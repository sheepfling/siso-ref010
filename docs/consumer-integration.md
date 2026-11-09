# Consume SISO-REF-010 data

This example shows a small application using an edition to interpret a DIS
Entity Type code. It uses only the public Python API and bundled data.

## Run the example

From the repository root:

    python -m pip install -e .
    python -m examples.entity_type_consumer
    python -m examples.entity_type_consumer --standard-version 35
    python -m examples.entity_type_consumer --entity-type 1.2.225.1.3.255.0

The last command uses a code with an unrecognized component. The example
reports what matched and which field is unresolved; it does not replace the
input with a nearby match.

## Use the API

Select the edition your application has agreed to use, then inspect a complete
seven-field code:

    from siso_ref010 import EntityType, SisoRef010API, ResolutionStatus

    api = SisoRef010API.bundled(37)
    code = EntityType.from_string("1.2.225.1.3.3.4")
    result = api.explain_entity(code)
    resolution = result.resolution

    if resolution.status is ResolutionStatus.EXACT:
        print(result.qualified_description)
    else:
        print(resolution.human_outcome)
        print("Unresolved fields:", resolution.unresolved_components)

EntityType validates and preserves the numeric fields. explain_entity()
returns the resolution status, matched hierarchy, and any unspecified or
unresolved fields. Check the status before treating a description as the
meaning of the complete code: a matched hierarchy can describe only a known
ancestor.

EntityType.to_bytes() returns the eight bytes for the Entity Type field. It
does not construct a complete DIS PDU or send data anywhere. The application
remains responsible for its own validation and acceptance policy.

Use one SisoRef010API for the selected edition and reuse it. An edition is a
data snapshot, not a DIS protocol version. See the [API guide](api.md) and
[source provenance notes](provenance.md) for more detail.
