# FinPilot formula reference

FinPilot evaluates formulas with its own safe engine. Learner input is tokenized and parsed into a syntax
tree; nothing is ever passed to Python's `eval` or `exec`. Text that is not a valid formula is reported as a
syntax problem and never executed.

## Syntax

- Formulas start with `=`. Cell references: `B4`, `$B$4` (absolute), `B$4` / `$B4` (mixed); ranges
  `B10:M10`. Up to 500 rows and 52 columns (A to AZ).
- Named ranges (Lab: **Name…**), e.g. `ROOMS` = `B4`, then `=ROOMS*B9`.
- Operators, highest precedence first (same as Excel): range `:`, negation `-`, percent `%`, power `^`,
  `*` `/`, `+` `-`, concatenation `&`, comparisons `=` `<>` `<` `>` `<=` `>=`.
  So `=-2^2` is 4 and `=2^3^2` is 64, exactly as in Excel.
- Text in double quotes (`"Jan"`, `""` for an empty string), `TRUE` / `FALSE`.
- Blank cells count as 0 in arithmetic and as empty text in text functions.

## Supported functions (56)

| Group | Functions |
|---|---|
| Math | `SUM`, `AVERAGE`, `MIN`, `MAX`, `COUNT`, `COUNTA`, `COUNTBLANK`, `ROUND`, `ROUNDUP`, `ROUNDDOWN`, `ABS`, `INT`, `MOD`, `POWER`, `SQRT`, `SUMPRODUCT` |
| Logic | `IF`, `IFS`, `IFERROR`, `IFNA`, `AND`, `OR`, `NOT`, `ISBLANK`, `ISERROR`, `ISNUMBER`, `NA` |
| Conditional | `SUMIF`, `SUMIFS`, `COUNTIF`, `COUNTIFS`, `AVERAGEIF`, `AVERAGEIFS` (criteria like `">2"`, `"<>x"`, `"=5"`) |
| Lookup | `MATCH`, `INDEX`, `XLOOKUP`, `VLOOKUP`, `HLOOKUP` |
| Dates | `DATE`, `YEAR`, `MONTH`, `DAY`, `EOMONTH`, `EDATE`, `DAYS` (Excel 1900 date serials) |
| Finance | `PMT`, `FV`, `PV`, `NPV`, `IRR` |
| Text | `CONCAT`, `LEN`, `UPPER`, `LOWER`, `LEFT`, `RIGHT` |

`IF`, `IFS`, `IFERROR` and `IFNA` evaluate only the branch they need, so `=IF(B1=0,0,A1/B1)` never produces
`#DIV/0!`.

## Explicitly unsupported

These Excel functions are recognised and return **`#UNSUPPORTED!`** with an explanation (they are never
silently treated as something else): `AGGREGATE`, `CELL`, `CHOOSE`, `FILTER`, `FORECAST`, `GETPIVOTDATA`,
`GROWTH`, `INDIRECT`, `LAMBDA`, `LET`, `LINEST`, `MEDIAN`, `NETWORKDAYS`, `NOW`, `NPER`, `OFFSET`,
`PERCENTILE`, `RAND`, `RANDBETWEEN`, `RATE`, `SEQUENCE`, `SORT`, `STDEV`, `STDEV.S`, `SUBTOTAL`, `TEXT`,
`TEXTJOIN`, `TODAY`, `TREND`, `UNIQUE`, `WORKDAY`, `XIRR`, `XNPV`. Any other unknown name returns `#NAME?`.

Volatile and reference-building functions (`OFFSET`, `INDIRECT`, `NOW`, `TODAY`, `RAND`) are excluded on
purpose: they make models hard to audit, and the curriculum teaches stable alternatives (`INDEX`, fixed
dates as inputs).

## Error values

| Code | Category | Meaning |
|---|---|---|
| `#DIV/0!` | math | Division by zero or by a blank cell. Fix: check the denominator, or guard with `IF(den=0, …)`. |
| `#VALUE!` | input | Wrong type, e.g. text in arithmetic. |
| `#REF!` | formula | Reference outside the sheet (for example after a copy past column AZ). |
| `#NAME?` | formula | Unknown function or name (typo, or a name not defined). |
| `#N/A` | missing | Lookup value not found. |
| `#NUM!` | math | Invalid numeric result (square root of a negative, IRR that does not converge). |
| `#CIRC!` | formula | Circular reference: the cell depends on itself. FinPilot does not iterate. |
| `#UNSUPPORTED!` | formula | Excel function FinPilot does not implement (see above). |
| `#PARSE!` | formula | The formula could not be read (brackets, commas, operators). |

Errors propagate through dependent formulas as in Excel. The Lab's status line counts error cells by
category; **Explain** on a cell shows what it contains, the values it reads and its result.

## Excel export

Exported workbooks contain the same formulas. Functions introduced after Excel 2007 (for example `XLOOKUP`,
`IFS`, `CONCAT`) are written with Excel's `_xlfn.` prefix so Excel recognises them. Workbooks are flagged to
recalculate fully when opened. FinPilot does not run Microsoft Excel; the test suite verifies exports by
re-reading them into FinPilot's engine and, where LibreOffice is installed, by a LibreOffice headless
recalculation.
