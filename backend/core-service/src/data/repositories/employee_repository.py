import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import case, func, or_, select, text

from src.data.models import Employee
from src.data.repositories.base import BaseRepository

FUZZY_SEARCH_MIN_CHARS = 3  # shorter searches only match text that is in the name
FUZZY_SEARCH_MIN_SIMILARITY = 0.3


class EmployeeRepository(BaseRepository[Employee]):
    model = Employee

    async def get_by_code(self, company_id: uuid.UUID, code: str) -> Employee | None:
        return await self.session.scalar(
            select(Employee).where(
                Employee.company_id == company_id,
                func.lower(Employee.employee_code) == code.strip().lower(),
            )
        )

    async def get_by_email(self, company_id: uuid.UUID, email: str) -> Employee | None:
        return await self.session.scalar(
            select(Employee).where(
                Employee.company_id == company_id,
                Employee.email == email.strip().lower(),
            )
        )

    async def search(
        self,
        *,
        company_id: uuid.UUID | None,
        q: str | None,
        is_active: bool | None,
        page: int,
        size: int,
    ) -> tuple[Sequence[Employee], int]:
        query = select(Employee)
        if company_id is not None:
            query = query.where(Employee.company_id == company_id)
        if is_active is not None:
            query = query.where(Employee.is_active.is_(is_active))
        order: list[Any] = [Employee.full_name, Employee.id]
        if q and q.strip():
            pattern = f"%{q.strip()}%"
            contains = or_(
                Employee.full_name.ilike(pattern),
                Employee.employee_code.ilike(pattern),
                Employee.email.ilike(pattern),
                func.array_to_string(Employee.aliases, " ").ilike(pattern),
            )
            if len(q.strip()) >= FUZZY_SEARCH_MIN_CHARS:
                # Close spellings too ("Jon Smth" finds John Smith), best first; text
                # that is in the name still comes before a close spelling.
                best = func.public.word_similarity(
                    func.core.name_key(q.strip()), Employee.name_keys
                )
                query = query.where(or_(contains, best >= FUZZY_SEARCH_MIN_SIMILARITY))
                order = [case((contains, 0), else_=1), best.desc().nulls_last(), *order]
            else:
                query = query.where(contains)
        return await self.paginate(query.order_by(*order), page=page, size=size)

    async def list_active(self, company_id: uuid.UUID) -> Sequence[Employee]:
        """Everyone matching may pick from: the company's active employees."""
        rows = await self.session.scalars(
            select(Employee).where(
                Employee.company_id == company_id, Employee.is_active.is_(True)
            )
        )
        return rows.all()

    async def similar_names(
        self,
        name: str,
        *,
        company_id: uuid.UUID | None,
        min_similarity: float,
        limit: int = 10,
    ) -> list[tuple[uuid.UUID, uuid.UUID, float]]:
        """Active employees (of active companies) whose full name or an alias looks like
        `name` by trigrams (pg_trgm): [(employee_id, company_id, similarity)], best
        first. company_id=None searches every company.

        employees.name_keys holds all of an employee's names in one text, so this uses
        word_similarity (the best-matching part of that text: an alias scores fully next
        to the full name) and its operator <%, which the GIN index serves; the threshold
        is set for this transaction only."""
        await self.session.execute(
            text("SELECT set_config('pg_trgm.word_similarity_threshold', :t, true)"),
            {"t": str(min_similarity)},
        )
        rows = await self.session.execute(
            text(
                """
                SELECT e.id, e.company_id,
                       public.word_similarity(
                           core.name_key(:name), e.name_keys
                       ) AS score
                FROM core.employees e
                JOIN core.companies c ON c.id = e.company_id
                WHERE core.name_key(:name) OPERATOR(public.<%) e.name_keys
                  AND e.is_active AND c.is_active
                  AND (CAST(:company_id AS uuid) IS NULL OR e.company_id = :company_id)
                ORDER BY score DESC, e.id
                LIMIT :limit
                """
            ),
            {"name": name, "company_id": company_id, "limit": limit},
        )
        return [(r[0], r[1], float(r[2])) for r in rows.all()]
