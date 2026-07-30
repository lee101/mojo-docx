from __future__ import annotations


class Length(int):
    @property
    def inches(self) -> float:
        return self / 914400

    @property
    def cm(self) -> float:
        return self / 360000

    @property
    def mm(self) -> float:
        return self / 36000

    @property
    def pt(self) -> float:
        return self / 12700

    @property
    def emu(self) -> int:
        return int(self)

    @property
    def twips(self) -> int:
        return int(round(self / 635))


class Inches(Length):
    def __new__(cls, inches: float):
        return Length.__new__(cls, int(round(inches * 914400)))


class Cm(Length):
    def __new__(cls, cm: float):
        return Length.__new__(cls, int(round(cm * 360000)))


class Mm(Length):
    def __new__(cls, mm: float):
        return Length.__new__(cls, int(round(mm * 36000)))


class Pt(Length):
    def __new__(cls, points: float):
        return Length.__new__(cls, int(round(points * 12700)))


class Emu(Length):
    pass


class RGBColor(tuple):
    def __new__(cls, r: int, g: int, b: int):
        values = (r, g, b)
        if any(not 0 <= component <= 255 for component in values):
            raise ValueError("RGB components must be in 0..255")
        return tuple.__new__(cls, values)

    @classmethod
    def from_string(cls, rgb_hex_str: str) -> "RGBColor":
        if len(rgb_hex_str) != 6:
            raise ValueError("RGB string must contain exactly six hex digits")
        return cls(*(int(rgb_hex_str[i : i + 2], 16) for i in (0, 2, 4)))

    def __str__(self) -> str:
        return "".join(f"{component:02X}" for component in self)
