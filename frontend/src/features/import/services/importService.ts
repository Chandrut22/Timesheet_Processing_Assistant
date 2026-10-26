// Bulk import (admins): the CSV template, and importing one CSV / XLSX file.
//   users                         -> auth-service  /users/import
//   employees, companies, holidays -> core-service /api/{resource}/import
import { filenameFromDisposition, http, saveBlob } from "@/lib/axios";
import {
  ImportReportSchema,
  type ImportOptions,
  type ImportReport,
  type ImportResource,
} from "../types/import";
import { responseOf } from "@/services/response";

const BASE: Record<ImportResource, string> = {
  users: "/users",
  employees: "/api/employees",
  companies: "/api/companies",
  holidays: "/api/holidays",
};

export const importService = {
  downloadTemplate: async (resource: ImportResource): Promise<void> => {
    const res = await http.get<Blob>(`${BASE[resource]}/import/template`, {
      responseType: "blob",
    });
    const name =
      filenameFromDisposition(res.headers["content-disposition"]) ||
      `${resource}-import-template.csv`;
    saveBlob(res.data, name);
  },

  /** dryRun=true checks the file and writes nothing; the report says what would happen. */
  importFile: (
    resource: ImportResource,
    file: File,
    options: ImportOptions,
  ): Promise<ImportReport> => {
    const form = new FormData();
    form.append("file", file);
    return http
      .post(`${BASE[resource]}/import`, form, {
        params: {
          dry_run: options.dryRun,
          on_error: options.onError,
          on_duplicate: options.onDuplicate,
        },
      })
      .then(responseOf(ImportReportSchema));
  },
};
