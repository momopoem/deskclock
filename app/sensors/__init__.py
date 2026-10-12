"""Hardware sensor workers, one module per physical device."""
from .aht21 import fetch_aht21_loop
from .bh1750 import fetch_bh1750_loop
from .bme280 import fetch_bme280_loop
from .ens160 import fetch_ens160_loop
from .pir import fetch_pir_loop
from .scd40 import fetch_scd40_loop
from .sht20 import fetch_sht20_loop

__all__ = [
    "fetch_aht21_loop", "fetch_bh1750_loop", "fetch_bme280_loop",
    "fetch_ens160_loop", "fetch_pir_loop", "fetch_scd40_loop",
    "fetch_sht20_loop",
]
