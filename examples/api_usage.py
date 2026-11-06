"""Run after installing: python examples/api_usage.py"""

from siso_entity_type.api import Collection, EntityTypeAPI, decode_key, encode_entity


def main() -> None:
    api = EntityTypeAPI()
    details = api.describe("1.3.153.6.4.2.0")
    print(details.qualified_description)
    print(api.search("F803", limit=10).hits)
    print(api.choices(Collection.CATEGORIES, 1, 4, 153).items)
    encoding = encode_entity(details.entity)
    assert decode_key(encoding.key).entity == details.entity
    print(encoding.to_dict())


if __name__ == "__main__":
    main()
