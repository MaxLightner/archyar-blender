"""The exact metadata IDs and dimensions of Archyar's Android furniture catalog.

Source: MaxLightner/archyar FurnitureCatalog.java at main, 2026-10-23.
Models are lightweight procedural reconstructions, not extracted GLB assets.
"""

from dataclasses import dataclass


SOURCE_REPOSITORY = "MaxLightner/archyar"
FURNITURE_ORIGIN = "chido-procedural-v0.5"
PALETTE = ((.714, .737, .635), (.835, .769, .678), (.725, .769, .776), (.729, .576, .502))


@dataclass(frozen=True)
class Asset:
    index: int
    name: str
    category: str
    template: str
    width: float
    height: float
    depth: float
    wall_mounted: bool = False


FURNITURE = (
    Asset(0, "Sofa", "seating", "sofa", 2.10, .85, .90),
    Asset(1, "Armchair", "seating", "armchair", .90, .85, .90),
    Asset(2, "Table", "tables", "table", 1.10, .40, .60),
    Asset(3, "Armchair Variant", "seating", "armchair", .90, .85, .90),
    Asset(4, "Ceramic Vase", "decor", "vase", .25, .40, .25),
    Asset(5, "Decorative Cushion", "decor", "pillow", .46, .18, .40),
    Asset(6, "Floor Lamp", "lighting", "floor-lamp", .45, 1.55, .45),
    Asset(7, "Minimal Rug", "rugs", "rug", 2.40, .015, 1.70),
    Asset(8, "Double Bed", "bedroom", "bed", 1.65, .95, 2.08),
    Asset(9, "Desk", "workspace", "desk", 1.40, .74, .67),
    Asset(10, "Dining Table", "dining", "dining-table", 1.70, .75, .86),
    Asset(11, "Dining Chair", "dining", "chair", .48, .90, .47),
    Asset(12, "Square Side Table", "tables", "side-table", .48, .48, .48),
    Asset(13, "Square Coffee Table", "tables", "coffee-table", 1.15, .42, 1.15),
    Asset(14, "Table Lamp", "lighting", "desk-lamp", .35, .55, .35),
    Asset(15, "Tripod Lamp", "lighting", "tripod-lamp", .55, 1.60, .55),
    Asset(16, "Small Portrait Art", "wall-art", "art", .45, .68, .045, True),
    Asset(17, "Small Landscape Art", "wall-art", "art", .70, .44, .045, True),
    Asset(18, "Medium Square Art", "wall-art", "art", .65, .65, .045, True),
    Asset(19, "Large Landscape Art", "wall-art", "art", 1.20, .68, .045, True),
    Asset(20, "Large Portrait Art", "wall-art", "art", .78, 1.15, .045, True),
    Asset(21, "Triptych Art", "wall-art", "triptych", 1.25, .75, .045, True),
)

CATEGORY_NAMES = {
    "seating": "Seating", "tables": "Tables", "decor": "Decor", "lighting": "Lighting",
    "rugs": "Rugs", "bedroom": "Bedroom", "workspace": "Workspace",
    "dining": "Dining", "wall-art": "Wall Art",
}
WALL_PRESETS = {"wall": ("Aerated Block Wall", .15), "partition": ("Interior Partition", .10), "block": ("Concrete Block Wall", .20)}
OPENINGS = {"fixed": "Fixed Window", "sliding": "Sliding Window", "hinged": "Hinged Window", "arched": "Arched Window", "door": "Hinged Door", "sliding-door": "Sliding Door"}
BUILD_PARTS = {"column": "Column", "floor": "Floor", "ceiling": "Ceiling", "stairs": "Straight Stair", "railing": "Railing"}


def furniture(index):
    if not isinstance(index, int) or not 0 <= index < len(FURNITURE):
        raise ValueError("Unknown Archyar furniture index")
    return FURNITURE[index]


def validate_catalog():
    assert len(FURNITURE) == 22
    assert [a.index for a in FURNITURE] == list(range(22))
    assert all(a.width > 0 and a.height > 0 and a.depth > 0 for a in FURNITURE)


validate_catalog()
