"""Build docs/scenario-check.xlsx: the Tsho Rolpa breach scenario and the Rasuwa What-if rule as a spreadsheet with live formulas.

usage: python build_scenario_check.py [--check]
Reads data/qa/tsho-rolpa-2026-scenario-sections.csv, data/qa/rasuwa-2026-simulation-features.csv and the Tsho Rolpa manifest.
With --check it then evaluates every formula (with the `formulas` package, no spreadsheet program needed) and compares the
results with the manifest and the three documented What-if settings. It exits with an error if any differ.

The depths, widths and areas in the Sections sheet come from the Python bisection: a spreadsheet cannot solve Manning for the
depth on a terrain profile. Everything after them (R, v, segment time, cumulative time, arrival minutes) is a live formula.
"""
import csv
import json
import pathlib
import sys

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.worksheet.table import Table

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/scenario-check.xlsx"
SECTIONS = ROOT / "data/qa/tsho-rolpa-2026-scenario-sections.csv"
FEATURES = ROOT / "data/qa/rasuwa-2026-simulation-features.csv"
MANIFEST = ROOT / "frontend/public/data/manifests/tsho-rolpa-2026.json"
SETTINGS = [(25, 198), (10, 74), (50, 35)]
CHECK_KM = (10.0, 50.0, 107.0)
BOLD = Font(bold=True)


def num(v):
    try:
        f = float(v)
        return int(f) if f.is_integer() else f
    except ValueError:
        return v


def build():
    sc = json.loads(MANIFEST.read_text(encoding="utf-8"))["lake"]["scenario"]
    wb = Workbook()

    # Inputs
    ws = wb.active
    ws.title = "Inputs"
    lo, mean, hi = sc["areaRangeKm2"]
    rows = [("Input", "Value", "Unit", "Source"),
            ("Lake area, low", lo, "km²", "Lowest 'low' of the NISAR method range over four dates"),
            ("Lake area, mean", mean, "km²", "Mean of the four NISAR GCOV dates"),
            ("Lake area, high", hi, "km²", "Highest 'high' of the NISAR method range over four dates"),
            ("Breach depth 1", 10, "m", "Assumed"),
            ("Breach depth 2", 20, "m", "Assumed"),
            ("Breach depth 3", 30, "m", "Assumed"),
            ("Unit weight of water γ", sc["gammaNm3"], "N/m³", "ρg, as Costa and Schuster (1988) use it"),
            ("Manning n, smooth (fastest)", sc["roughness"][0], "s/m^(1/3)", "Steep boulder channels, Chow (1959)"),
            ("Manning n, rough (slowest)", sc["roughness"][1], "s/m^(1/3)", "Steep boulder channels, Chow (1959)"),
            ("Slope floor", sc["slopeFloor"], "m/m", "The bed slope is never taken below this"),
            ("Speed floor", sc["speedFloorMs"], "m/s", "The front is never taken slower than this"),
            ("Kinematic factor c/v", "=5/3", "", "Wide-channel Manning wave speed. Sensitivity only")]
    for r in rows:
        ws.append(r)
    for c in ws[1]:
        c.font = BOLD
    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["D"].width = 60
    ws.append([])
    ws.append(["A scenario, not a prediction. Change an input and the Peak flows sheet recalculates."])
    A = {"low": "Inputs!$B$2", "mean": "Inputs!$B$3", "high": "Inputs!$B$4"}
    H = ["Inputs!$B$5", "Inputs!$B$6", "Inputs!$B$7"]
    GAMMA, N_FAST, N_SLOW, S_FLOOR, V_FLOOR = "Inputs!$B$8", "Inputs!$B$9", "Inputs!$B$10", "Inputs!$B$11", "Inputs!$B$12"

    # Peak flows
    pf = wb.create_sheet("Peak flows")
    pf.append(["Breach depth (m)", "Area", "Area (km²)", "V (m³)", "Popov (m³/s)", "Costa PE (J)", "Costa (m³/s)", "Huggel (m³/s)", "Manifest Popov", "Manifest Costa", "Manifest Huggel", "Match"])
    for c in pf[1]:
        c.font = BOLD
    ranges = []
    for i, case in enumerate(sc["scenarios"]):
        first = pf.max_row + 1
        for name in ("low", "mean", "high"):
            r = pf.max_row + 1
            want = case["peaksByArea"][name]
            pf.append([f"={H[i]}", name, f"={A[name]}", f"=C{r}*1000000*A{r}", f"=0.0048*D{r}^0.896", f"=A{r}*D{r}*{GAMMA}", f"=0.0158*F{r}^0.41", f"=0.00077*D{r}^1.017",
                       want["popov"], want["costa"], want["huggel"], f"=AND(ROUND(E{r},0)=I{r},ROUND(G{r},0)=J{r},ROUND(H{r},0)=K{r})"])
        ranges.append((first, first + 2))
    pf.append([])
    pf.append(["Breach depth (m)", "Likely peak, low (m³/s)", "Likely peak, high (m³/s)", "Worst case (m³/s)", "Manifest low", "Manifest high", "Manifest worst", "Match"])
    for c in pf[pf.max_row]:
        c.font = BOLD
    for i, (a, b) in enumerate(ranges):
        r = pf.max_row + 1
        case = sc["scenarios"][i]
        pf.append([f"={H[i]}", f"=MIN(E{a},G{a})", f"=MAX(E{b},G{b})", f"=H{b}", case["peakRange"][0], case["peakRange"][1], case["worstM3s"],
                   f"=AND(ROUND(B{r},0)=E{r},ROUND(C{r},0)=F{r},ROUND(D{r},0)=G{r})"])
    pf.append([])
    pf.append(["Likely range: the lower of Popov and Costa at the low area, to the higher of the two at the high area. Huggel is an upper envelope, the worst case only."])

    # Sections
    se = wb.create_sheet("Sections")
    with SECTIONS.open(encoding="utf-8") as fh:
        table = list(csv.DictReader(fh))
    head = ["breach_m", "km", "bed_m", "slope_S", "slope_floor_applied"]
    bound = ["Q_m3s", "n", "h_m", "width_m", "area_m2", "R_m", "v_ms", "seg_m", "seg_s", "cum_s", "cum_min", "arrival_min"]
    se.append(head + [f"fast_{c}" for c in bound] + [f"slow_{c}" for c in bound])
    for c in se[1]:
        c.font = BOLD
    letters = lambda i: se.cell(row=1, column=i).column_letter  # noqa: E731
    for k, row in enumerate(table):
        r = k + 2
        vals = [num(row["breach_m"]), num(row["km"]), num(row["bed_m"]), f"=MAX({num(row['slope_raw'])},{S_FLOOR})", f"=IF({num(row['slope_raw'])}<{S_FLOOR},1,0)"]
        for b, start in (("fast", 6), ("slow", 18)):
            col = {name: letters(start + j) for j, name in enumerate(bound)}
            n_ref = N_FAST if b == "fast" else N_SLOW
            prev = f"IF(A{r - 1}=A{r},{col['cum_s']}{r - 1},0)" if r > 2 else "0"
            vals += [num(row[f"{b}_Q_m3s"]), f"={n_ref}", num(row[f"{b}_h_m"]), num(row[f"{b}_width_m"]), num(row[f"{b}_area_m2"]),
                     f"={col['area_m2']}{r}/({col['width_m']}{r}+2*{col['h_m']}{r})",
                     f"={col['R_m']}{r}^(2/3)*D{r}^0.5/{col['n']}{r}",
                     num(row[f"{b}_seg_m"]),
                     f"={col['seg_m']}{r}/MAX({col['v_ms']}{r},{V_FLOOR})",
                     f"={prev}+{col['seg_s']}{r}",
                     f"={col['cum_s']}{r}/60",
                     f"=ROUND({col['cum_min']}{r},0)"]
        se.append(vals)
    last = len(table) + 1
    se.freeze_panes = "C2"

    # Arrival check
    ac = wb.create_sheet("Arrival check")
    ac.append(["Breach depth (m)", "km", "Fastest (min), rebuilt", "Slowest (min), rebuilt", "Fastest, manifest", "Slowest, manifest", "Kinematic fastest (min)", "Kinematic slowest (min)", "Match"])
    for c in ac[1]:
        c.font = BOLD
    fast_min, slow_min = letters(6 + bound.index("cum_min")), letters(18 + bound.index("cum_min"))
    for i, case in enumerate(sc["scenarios"]):
        for km in CHECK_KM:
            r = ac.max_row + 1
            want = next(a for a in case["arrival"] if a[0] == km)
            f = f"SUMIFS(Sections!${fast_min}$2:${fast_min}${last},Sections!$A$2:$A${last},A{r},Sections!$B$2:$B${last},B{r})"
            s = f"SUMIFS(Sections!${slow_min}$2:${slow_min}${last},Sections!$A$2:$A${last},A{r},Sections!$B$2:$B${last},B{r})"
            ac.append([f"={H[i]}", km, f"=ROUND({f},0)", f"=ROUND({s},0)", want[1], want[2], f"=ROUND({f}/Inputs!$B$13,0)", f"=ROUND({s}/Inputs!$B$13,0)", f"=AND(C{r}=E{r},D{r}=F{r})"])
    ac.append([])
    ac.append(["The method moves the front at the water speed v and never reduces the peak downstream. These two errors push the times in opposite directions."])
    ac.append(["The kinematic columns divide by 5/3 (the wide-channel wave speed): a sensitivity line, not the default."])

    # Rasuwa
    ra = wb.create_sheet("Rasuwa")
    with FEATURES.open(encoding="utf-8") as fh:
        feats = list(csv.reader(fh))
    n = len(feats)
    ra["I1"], ra["J1"] = "Rise (m)", 25
    ra["I2"], ra["J2"] = "Reach (km)", 198
    ra["I3"], ra["J3"] = "Buildings", f'=COUNTIFS($A$2:$A${n},"b",$C$2:$C${n},"<="&J2,$D$2:$D${n},"<="&J1)'
    ra["I4"], ra["J4"] = "OSM road (km)", f'=SUMIFS($E$2:$E${n},$A$2:$A${n},"r",$C$2:$C${n},"<="&J2,$D$2:$D${n},"<="&J1)'
    ra["I5"], ra["J5"] = "Places", f'=COUNTIFS($A$2:$A${n},"p",$C$2:$C${n},"<="&J2,$D$2:$D${n},"<="&J1)'
    ra["I7"] = "The rule: a row counts when km <= reach AND h <= rise. Buildings counted, OSM road pieces (r) add len, places listed."
    ra["I9"], ra["J9"], ra["K9"], ra["L9"], ra["M9"], ra["N9"] = "Setting", "Rise", "Reach", "Buildings", "OSM road (km)", "Places"
    for c in ra[9][8:14]:
        c.font = BOLD
    for j, (rise, reach) in enumerate(SETTINGS):
        r = 10 + j
        ra[f"I{r}"], ra[f"J{r}"], ra[f"K{r}"] = f"Rise {rise} m, reach {reach} km", rise, reach
        ra[f"L{r}"] = f'=COUNTIFS($A$2:$A${n},"b",$C$2:$C${n},"<="&K{r},$D$2:$D${n},"<="&J{r})'
        ra[f"M{r}"] = f'=SUMIFS($E$2:$E${n},$A$2:$A${n},"r",$C$2:$C${n},"<="&K{r},$D$2:$D${n},"<="&J{r})'
        ra[f"N{r}"] = f'=COUNTIFS($A$2:$A${n},"p",$C$2:$C${n},"<="&K{r},$D$2:$D${n},"<="&J{r})'
    for k, row in enumerate(feats):
        for j, v in enumerate(row):
            ra.cell(row=k + 1, column=j + 1, value=v if k == 0 or j in (0, 1) else num(v) if v != "" else None)
    for c in ra[1][:7]:
        c.font = BOLD
    ra.add_table(Table(displayName="Features", ref=f"A1:G{n}"))
    ra.freeze_panes = "A2"
    OUT.parent.mkdir(exist_ok=True)
    wb.save(OUT)
    (ROOT / "frontend/public/data/working").mkdir(parents=True, exist_ok=True)
    (ROOT / "frontend/public/data/working/scenario-check.xlsx").write_bytes(OUT.read_bytes())
    return OUT


def check(path: pathlib.Path) -> list[str]:
    """Evaluate every formula and compare with the manifest and the documented What-if counts."""
    import formulas

    sol = formulas.ExcelModel().loads(str(path)).finish().calculate()
    book = f"[{path.name}]"

    def val(sheet, cell):
        v = sol[f"'{book}{sheet.upper()}'!{cell}"].value
        return v[0][0] if hasattr(v, "__len__") else v

    errors = []
    for r in range(2, 11):
        if val("Peak flows", f"L{r}") != True:  # noqa: E712 (the evaluator returns its own boolean type)
            errors.append(f"Peak flows row {r} differs from the manifest")
    for r in range(13, 16):
        if val("Peak flows", f"H{r}") != True:  # noqa: E712 (the evaluator returns its own boolean type)
            errors.append(f"Peak range row {r} differs from the manifest")
    for r in range(2, 2 + 3 * len(CHECK_KM)):
        if val("Arrival check", f"I{r}") != True:  # noqa: E712 (the evaluator returns its own boolean type)
            errors.append(f"Arrival row {r}: rebuilt {val('Arrival check', f'C{r}')}-{val('Arrival check', f'D{r}')}, manifest {val('Arrival check', f'E{r}')}-{val('Arrival check', f'F{r}')}")
    want = {10: (3274, 119.339, 8), 11: (489, 11.305, 1), 12: (553, 25.265, 2)}
    for r, (b, road, p) in want.items():
        got = (val("Rasuwa", f"L{r}"), round(float(val("Rasuwa", f"M{r}")), 3), val("Rasuwa", f"N{r}"))
        if got != (b, road, p):
            errors.append(f"Rasuwa row {r}: {got}, expected {(b, road, p)}")
    return errors


if __name__ == "__main__":
    out = build()
    print(f"Wrote {out.relative_to(ROOT)}")
    if "--check" in sys.argv:
        errs = check(out)
        if errs:
            sys.exit("\n".join(errs))
        print("Every formula evaluates to the manifest's numbers and the three documented What-if counts.")
