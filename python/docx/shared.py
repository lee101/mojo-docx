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


# Matches docx.shared.Inches/Cm/Mm/Pt: upstream builds EMU with int(value * EMU_PER_UNIT)
# (truncation toward zero), not round(); e.g. Inches(0.0000007) == 0 upstream.
class Inches(Length):
    def __new__(cls, inches: float):
        return Length.__new__(cls, int(inches * 914400))


class Cm(Length):
    def __new__(cls, cm: float):
        return Length.__new__(cls, int(cm * 360000))


class Mm(Length):
    def __new__(cls, mm: float):
        return Length.__new__(cls, int(mm * 36000))


class Pt(Length):
    def __new__(cls, points: float):
        return Length.__new__(cls, int(points * 12700))


class Emu(Length):
    pass


class RGBColor(tuple):
    def __new__(cls, r: int, g: int, b: int):
        # Matches docx.shared.RGBColor: non-integer components raise TypeError
        # ("RGBColor() takes three integer values 0-255"); out-of-range raise ValueError.
        values = (r, g, b)
        if any(not isinstance(component, int) for component in values):
            raise TypeError("RGBColor() takes three integer values 0-255")
        if any(not 0 <= component <= 255 for component in values):
            raise ValueError("RGBColor() takes three integer values 0-255")
        return tuple.__new__(cls, values)

    @classmethod
    def from_string(cls, rgb_hex_str: str) -> "RGBColor":
        # Matches docx.shared.RGBColor.from_string: slice into three hex pairs and let
        # int(..., 16) / the component range check raise ValueError; e.g. "123" and
        # "1234567" fail downstream rather than on a length check here.
        return cls(*(int(rgb_hex_str[i : i + 2], 16) for i in (0, 2, 4)))

    def __str__(self) -> str:
        return "".join(f"{component:02X}" for component in self)
