"""Keep one physical-sensor implementation per app/sensors module."""
from pathlib import Path


ROOT = Path(__file__).parents[1]
SENSORS = {
    "aht21.py": "fetch_aht21_loop",
    "bh1750.py": "fetch_bh1750_loop",
    "bme280.py": "fetch_bme280_loop",
    "ens160.py": "fetch_ens160_loop",
    "pir.py": "fetch_pir_loop",
    "scd40.py": "fetch_scd40_loop",
    "sht20.py": "fetch_sht20_loop",
}


def test_each_hardware_worker_has_a_dedicated_sensor_module():
    for filename, worker in SENSORS.items():
        source = (ROOT / "app" / "sensors" / filename).read_text(encoding="utf-8")
        assert f"def {worker}(" in source


def test_production_startup_imports_sensor_workers_from_sensors_package():
    for relative in ("app/clock.py", "app/services/sensor_manager.py"):
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "from sensors import (" in source


def test_legacy_sensor_service_is_only_a_compatibility_facade():
    source = (ROOT / "app/services/sensor_service.py").read_text(encoding="utf-8")
    assert "from sensors import" in source
    assert "from smbus2 import" not in source
