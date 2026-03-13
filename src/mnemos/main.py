import asyncio

from mnemos.config import settings
from mnemos.server import mcp


def main() -> None:
    asyncio.run(
        mcp.run_http_async(
            host=settings.host,
            port=settings.port,
        )
    )


if __name__ == "__main__":
    main()
