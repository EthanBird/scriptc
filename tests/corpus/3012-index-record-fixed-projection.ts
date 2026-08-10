type TextBag = Record<string, string>;
type FixedText = { alpha: string; beta: string };
const textBag: TextBag = { alpha: "A", beta: "B", ignored: "X" };
const fixedText = textBag as FixedText;
console.log("text", fixedText.alpha, fixedText.beta);

type ColorValue = string | number;
type ColorBag = Record<string, ColorValue>;
type FixedTheme = { accent: ColorValue; border: ColorValue; warning: ColorValue };
const colors: ColorBag = { accent: "#fff", border: 8, warning: "yellow", extra: 99 };
const theme = colors as FixedTheme;
console.log("theme", theme.accent, theme.border, theme.warning);
