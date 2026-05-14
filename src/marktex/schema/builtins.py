from __future__ import annotations

from marktex.semantics import PAGE_SIZE_PRESETS
from marktex.schema.registry import CallSpec, ContextSpec, SchemaRegistry, ShadeSpec

LAYOUT_VALUE_SHADES = {
    name: ShadeSpec(
        name,
        lowerer="page_size",
        payload={"width": preset.width, "height": preset.height},
    )
    for name, preset in PAGE_SIZE_PRESETS.items()
} | {
    "landscape": ShadeSpec(
        "landscape",
        lowerer="orientation",
        payload={"orientation": "landscape"},
    ),
    "portrait": ShadeSpec("portrait", lowerer="orientation", payload={"orientation": "portrait"}),
}


def builtin_registry() -> SchemaRegistry:
    """Return a fresh built-in schema registry.

    Shorthand/no-arg behavior lives in data constants above. Adding page-size
    presets or style shorthands should change those constants, not the parser.
    """

    return SchemaRegistry(
        {
            "document": ContextSpec(
                "document",
                calls={
                    "layout": CallSpec("layout", "document_patch", invokable=True),
                    "margin": CallSpec("margin", "document_patch", invokable=True),
                    "bib": CallSpec("bib", "resource_set", invokable=True),
                    "bib+": CallSpec("bib+", "resource_add", invokable=True),
                    "bib-": CallSpec("bib-", "resource_remove", invokable=True),
                    "bibstyle": CallSpec("bibstyle", "document_patch", invokable=True),
                    "citestyle": CallSpec("citestyle", "document_patch", invokable=True),
                    "newpage": CallSpec("newpage", "page_break", accepts_raw_args=False),
                },
            ),
            "layout.value": ContextSpec("layout.value", shade=LAYOUT_VALUE_SHADES),
            "scope": ContextSpec("scope"),
            "reference": ContextSpec(
                "reference",
                calls={"cite": CallSpec("cite", "citation")},
            ),
            "table-column": ContextSpec("table-column"),
        }
    )
