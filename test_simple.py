import asyncio
from site_tgach.importer import ThreadImporter

async def test_importer():
    ThreadImporter()
    # It has local_address set, we just want to import and see if it passes syntax.
    print("Importer imported and instantiated")

asyncio.run(test_importer())
