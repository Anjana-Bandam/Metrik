"""
live_machine_simulator.py
----------------------------
Standalone script that mimics 5 CNC machines streaming live sensor data.

This is intentionally decoupled from FastAPI: run it on its own to watch
realistic JSON payloads print every 2 seconds, or import `generate_reading()`
/ `MachineSimState` elsewhere. main.py uses the same generation logic
internally (via an identical algorithm) to advance its in-memory machine
state on each /get_all_machines poll, so what you see here matches what
the dashboard shows.

Run directly:
    python backend/utils/live_machine_simulator.py
"""

import json
import random
import time
from dataclasses import dataclass, field


@dataclass
class MachineSimState:
    machine_id: str
    name: str
    material_type: str = "M"          # L / M / H
    spindle_speed: float = 1500.0
    spindle_torque: float = 40.0
    tool_runtime: float = 0.0         # minutes, climbs over time
    depth_of_cut: float = 1.2         # mm
    air_temperature: float = 300.1
    process_temperature: float = 310.1

    def step(self):
        """Advance this machine by one ~2-second tick with realistic jitter."""
        self.spindle_speed = max(800, self.spindle_speed + random.uniform(-15, 15))
        self.spindle_torque = max(5, self.spindle_torque + random.uniform(-1.2, 1.6))
        self.depth_of_cut = max(0.2, self.depth_of_cut + random.uniform(-0.05, 0.05))
        self.air_temperature += random.uniform(-0.05, 0.08)
        self.process_temperature += random.uniform(-0.05, 0.12)
        # Runtime only ever climbs while the machine is "cutting"
        self.tool_runtime += random.uniform(0.03, 0.12)

    def to_json(self) -> dict:
        return {
            "machine_id": self.machine_id,
            "name": self.name,
            "material_type": self.material_type,
            "spindle_speed": round(self.spindle_speed, 1),
            "spindle_torque": round(self.spindle_torque, 2),
            "tool_runtime": round(self.tool_runtime, 2),
            "depth_of_cut": round(self.depth_of_cut, 3),
            "air_temperature": round(self.air_temperature, 2),
            "process_temperature": round(self.process_temperature, 2),
        }


DEFAULT_FLEET = [
    MachineSimState("m-01", "Machine 1", material_type="L", tool_runtime=12),
    MachineSimState("m-02", "Machine 2", material_type="M", tool_runtime=45),
    MachineSimState("m-03", "Machine 3", material_type="H", tool_runtime=178),
    MachineSimState("m-04", "Machine 4", material_type="M", tool_runtime=6),
    MachineSimState("m-05", "Machine 5", material_type="L", tool_runtime=92),
]


def generate_reading(machine: MachineSimState) -> dict:
    machine.step()
    return machine.to_json()


if __name__ == "__main__":
    print("[Metrik] Live machine simulator started - Ctrl+C to stop.\n")
    try:
        while True:
            for m in DEFAULT_FLEET:
                reading = generate_reading(m)
                print(json.dumps(reading))
            print("-" * 60)
            time.sleep(2)
    except KeyboardInterrupt:
        print("\n[Metrik] Simulator stopped.")
