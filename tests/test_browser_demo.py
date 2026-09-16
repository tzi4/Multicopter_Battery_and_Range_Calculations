"""Keep the standalone HTML's numerical outputs aligned with the Python API.

Node executes the actual embedded application script with a minimal DOM/Plotly
adapter. This checks calculations; visual browser checks are documented in
AIRCRAFT_DEMO.md. Node is optional for local Python-only development.
"""

from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest

import multicopter_range as model
from examples import aircraft_inputs
from examples.reproduce_calibration import build_calibration_suite


ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
CASES = [(12.4, 29, 450), (10.93, 29, 450), (13, 29, 450),
         (8.2, 29, 450), (25, 29, 450), (12.4, 28, 450),
         (20, 28, 450), (12.4, 29, 300), (12.4, 29, 800), (12.4, 29, 450, "lihv")]


class Controls(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = {}
        self.selected = {}
        self.select_id = None

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if "id" in attrs:
            self.elements[attrs["id"]] = attrs
        if tag == "select":
            self.select_id = attrs["id"]
        if tag == "option" and "selected" in attrs:
            self.selected[self.select_id] = attrs["value"]

    def handle_endtag(self, tag):
        if tag == "select":
            self.select_id = None


NODE_ADAPTER = r"""
const fs = require('fs'), vm = require('vm');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const nodes = Object.fromEntries(Object.entries(input.elements).map(([id, attrs]) => [id, {
    ...attrs, value: attrs.value || '', textContent: '', innerHTML: '',
    addEventListener() {},
    appendChild(option) { if (!this.value || option.selected) this.value = option.value; }
}]));
for (const [id, value] of Object.entries(input.selected)) nodes[id].value = value;
const context = vm.createContext({
    document: {
        getElementById: id => nodes[id],
        createElement: () => ({}),
        addEventListener: (event, callback) => callback()
    },
    Plotly: { react: (id, data) => { nodes[id].data = data; } }
});
vm.runInContext(input.script, context, {timeout: 10000});
const defaults = Object.fromEntries(Object.entries(nodes).map(([id, node]) => [id, node.value]));
const cases = input.cases.map(([mass, prop, area, chemistry = "liion"]) => {
    nodes.batteryType.value = chemistry;
    nodes.massInputNum.value = String(mass);
    nodes.dragAreaInputNum.value = String(area);
    nodes.motorSelect.value = `u8lite_kv190_g${prop}_data`;
    vm.runInContext('calculate()', context, {timeout: 10000});
    return {mass, prop, area, chemistry, speeds: nodes.plotlyPowerRatio.data[0].x,
        ratios: nodes.plotlyPowerRatio.data[0].y,
        ranges: nodes.plotlyRangeTime.data[0].y,
        times: nodes.plotlyRangeTime.data[1].y,
        hover: nodes.cardHoverPower.textContent};
});
process.stdout.write(JSON.stringify({defaults, cases}));
"""


@pytest.mark.skipif(NODE is None, reason="Node.js is needed to compare HTML and Python calculations")
def test_standalone_demo_matches_current_fit_and_transferred_python_outputs():
    html = (ROOT / "docs/aircraft-demo.html").read_text(encoding="utf-8")
    controls = Controls()
    controls.feed(html)
    scripts = re.findall(r"<script>(.*?)</script>", html, flags=re.DOTALL)
    application = [script for script in scripts if "const MOTOR_DATASETS =" in script]
    assert len(application) == 1
    assert not re.search(r'<(?:script|link)[^>]+(?:src|href)="https?://', html)
    result = subprocess.run(
        [NODE, "-e", NODE_ADAPTER],
        input=json.dumps({"script": application[0], "elements": controls.elements,
                          "selected": controls.selected, "cases": CASES}),
        text=True, capture_output=True, check=True, timeout=30,
    )
    browser = json.loads(result.stdout)
    defaults = browser["defaults"]
    assert float(defaults["massInputNum"]) == aircraft_inputs.MASS_KG
    assert float(defaults["dragAreaInputNum"]) == aircraft_inputs.REFERENCE_AREA_CM2
    assert int(defaults["batteryArms"]) == aircraft_inputs.BATTERY_PACKS
    assert int(defaults["batteryS"]) == aircraft_inputs.CELLS_PER_PACK
    assert float(defaults["batteryMah"]) == aircraft_inputs.CAPACITY_MAH_PER_PACK
    assert defaults["motorSelect"] == "u8lite_kv190_g29_data"
    assert defaults["batteryType"] == aircraft_inputs.BATTERY_TYPE

    # Refit the public logs rather than trusting the coefficients embedded in HTML.
    suite = build_calibration_suite(ROOT / "data/calibration/2026-07-03")
    source = suite["model_profile"]
    params = suite["model_params"]["zeng_datalink_fit"]
    source_hover = suite["measured_hover_power_w"] * 2
    source_rpm, _ = model.datasheet_rpm_from_thrust(29, 3100)
    rpm_scale = params["utip_ms"] / model.tip_speed_from_rpm(29, source_rpm)
    electrical = aircraft_inputs.postflight_energy_basis()
    default_bench_w = aircraft_inputs.preflight_inputs()["hover_power_w"]

    for row in browser["cases"]:
        target = {**source, "mass_kg": row["mass"], "prop_diameter_inch": row["prop"]}
        rpm, _ = model.datasheet_rpm_from_thrust(row["prop"], row["mass"] * 1000 / 4)
        utip = model.tip_speed_from_rpm(row["prop"], rpm) * rpm_scale
        transferred = model.transfer_zeng_params_to_vehicle(params, source, source_hover, target, utip)
        physical = transferred["transfer"]
        # The original UI adds area changes to CdA with an incremental Cd of one.
        cda = physical["cda_parasite_m2"] + (row["area"] - 450) / 10000
        transferred["k_par"] = 0.5 * source["rho"] * cda / physical["hover_power_pred_w"]
        table = model.u8lite_kv190_g29_data if row["prop"] == 29 else model.u8lite_kv190_data
        bench_w = 4 * model.get_power_from_thrust(row["mass"] * 1000 / 4, table)
        hover_w = bench_w * electrical["hover_power_w"] / default_bench_w
        assert row["hover"] == f"{hover_w:.1f} W"
        assert len(row["speeds"]) == 2491
        ratios = [model.power_ratio_bauersfeld_anchored_zeng(v, transferred) for v in row["speeds"]]
        energy_wh = model.calculate_real_energy_wh(
            aircraft_inputs.BATTERY_PACKS * aircraft_inputs.CELLS_PER_PACK,
            aircraft_inputs.CAPACITY_MAH_PER_PACK, row["chemistry"],
        ) * (25.2 / 27.0) * (1 - aircraft_inputs.RESERVE_FRACTION)
        minutes = [60 * energy_wh / (hover_w * ratio) for ratio in ratios]
        ranges = [v * minute * 0.06 for v, minute in zip(row["speeds"], minutes)]
        assert row["ratios"] == pytest.approx(ratios, rel=1e-10, abs=1e-10)
        assert row["times"] == pytest.approx(minutes, rel=1e-10, abs=1e-10)
        assert row["ranges"] == pytest.approx(ranges, rel=1e-10, abs=1e-10)
