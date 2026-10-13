import logging


def configure_logging(level: str = "INFO") -> None:
    """Plain text logs on stdout. (JSON logs + request ids come later.)"""
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
