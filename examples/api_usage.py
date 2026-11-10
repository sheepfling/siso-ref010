"""Run from the repository root after installing: python -m examples.api_usage"""

from siso_ref010 import Collection, EntityTypePrefix, SisoRef010API, decode_key, encode_entity


def main() -> None:
    api = SisoRef010API()
    details = api.describe("1.3.153.6.4.2.0")
    print(details.qualified_description)
    for hit in api.search("F803", limit=10).hits:
        print(f"{hit.entity}: {hit.description}")
    category_parent = EntityTypePrefix(kind=1, domain=4, country=153)
    categories = api.choices(Collection.CATEGORIES, category_parent)
    print(tuple(choice.description for choice in categories.items))
    encoding = encode_entity(details.entity)
    assert decode_key(encoding.key).entity == details.entity
    print(encoding.model_dump(mode="json", by_alias=True))


if __name__ == "__main__":
    main()
