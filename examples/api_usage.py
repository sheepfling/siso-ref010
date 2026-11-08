"""Run after installing: python examples/api_usage.py"""

from siso_ref010 import EntityTypePrefix
from siso_ref010.api import Collection, EntityTypeAPI, decode_key, encode_entity


def main() -> None:
    api = EntityTypeAPI()
    details = api.describe("1.3.153.6.4.2.0")
    print(details.qualified_description)
    print(api.search("F803", limit=10).hits)
    category_parent = EntityTypePrefix(kind=1, domain=4, country=153)
    print(api.choices(Collection.CATEGORIES, category_parent).items)
    encoding = encode_entity(details.entity)
    assert decode_key(encoding.key).entity == details.entity
    print(encoding.model_dump(mode="json", by_alias=True))


if __name__ == "__main__":
    main()
