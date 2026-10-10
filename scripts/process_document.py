import argparse
import asyncio
import json
from uuid import UUID

from app.config.settings import Settings
from app.parsing.registered import parse_registered
from app.services.database import connect


async def main(document_id):
    connection = await connect(Settings())
    try:
        result = await parse_registered(connection, Settings(), UUID(document_id))
        print(json.dumps(result), flush=True)
    finally:
        await connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("document_id")
    asyncio.run(main(parser.parse_args().document_id))
