from enum import IntEnum


class WD_ORIENT(IntEnum):
    PORTRAIT = 0
    LANDSCAPE = 1


WD_ORIENTATION = WD_ORIENT


class WD_SECTION_START(IntEnum):
    CONTINUOUS = 0
    NEW_COLUMN = 1
    NEW_PAGE = 2
    EVEN_PAGE = 3
    ODD_PAGE = 4
