"""Top-level package for pyBuildingEnergy."""

from .source.check_input import sanitize_and_validate_BUI
from .source.utils import ISO52016
# .source.graphs is resolved lazily -- see the __getattr__ at the foot of this
# module. It is an optional charting layer, and importing it here made the whole
# engine unimportable wherever pyecharts is absent.
from .source.iso_15316_1 import HeatingSystemCalculator
from .source.emission_15316_2 import EmissionSimulationResult, EmissionSystemCalculator
from .source.distribution_15316_3 import DistributionSimulationResult, DistributionSystemCalculator
from .source.storage_15316_5 import StorageSimulationResult, StorageSystemCalculator
from .source.generation_15316_4_1 import BoilerConfig, BoilerGeneratorCalculator
from .source.cooling_16798_9 import CoolingSystemSimulationResult, CoolingSystemCalculator
from .source.cooling_storage_16798_15 import (
    CoolingStorageSimulationResult,
    CoolingStorageSystemCalculator,
)
from .source.cooling_generation_16798_13 import (
    CoolingGenerationSimulationResult,
    CoolingGenerationSystemCalculator,
)
from .source.performance_14511_14825 import (
    HeatPumpPerformanceDataCalculator,
    HeatPumpPerformanceDataResult,
    en14825_part_load_factor,
)
from .source.heat_pump_15316_4_2 import HeatPumpSimulationResult, HeatPumpSystemCalculator
from .source.combustion_15316_4_1 import (
    CombustionBoilerSimulationResult,
    CombustionBoilerSystemCalculator,
)
from .source.cogeneration_15316_4_4 import (
    CogenerationSimulationResult,
    CogenerationSystemCalculator,
)
from .source.district_15316_4_5 import (
    DistrictEnergySystemCalculator,
    DistrictSystemSimulationResult,
)
from .source.renewables_15316_4_3_4_6 import (
    RenewableEnergySimulationResult,
    RenewableEnergySystemCalculator,
)
from .source.primary_energy_52000_1 import (
    PrimaryEnergyAccountingCalculator,
    PrimaryEnergyAccountingResult,
)
from .source.lighting_15193_1 import (
    LightingSimulationResult,
    LightingSystemCalculator,
)
from .source.ventilation_16798_5_7 import (
    VentilationSystemCalculator,
    VentilationSystemSimulationResult,
)
from .source.bacs_52120_1 import (
    BACSControlFactorCalculator,
    BACSSimulationResult,
)
from .source.economics_15459_1 import (
    CostOptimalityCalculator,
    EconomicSimulationResult,
)
from .source.biomass_15316_4 import (
    BiomassBoilerSimulationResult,
    BiomassBoilerSystemCalculator,
)
from .data.italian_strepin import (
    ItalianStrepinTables,
    StrepinCase,
    apply_extra_measure_specs_to_bui,
    find_default_workbook,
    load_italian_strepin_tables,
    summarize_engine_performance,
)
from .source.check_input import check_heating_system_inputs
from .source.generate_profile import HourlyProfileGenerator, get_country_code_from_latlon
from .source.DHW import *
from .source.utils import *
from .source.ventilation import *
from .source.table_iso_16798_1 import *


__author__ = """Daniele Antonucci, Ulrich Filippi Oberagger, Olga Somova"""
__email__ = 'daniele.antonucci@eurac.edu'
__version__ = '2.0.3'


# ---------------------------------------------------------------------------
# Optional charting layer, resolved on first access (PEP 562)
# ---------------------------------------------------------------------------
# ``source.graphs`` imports pyecharts, and pyecharts is a rendering library: it
# is needed to draw a report, never to run a simulation. Importing it at package
# level made it a hard requirement of *everything*, so on any runtime without the
# charting stack -- a bare Colab session, a CI container -- `import
# pybuildingenergy.source.utils` failed outright. pytest reports that as a
# COLLECTION error and exits 2, which is not a test failure: the assertions never
# ran at all, and a suite that cannot load looks much like a suite that passes if
# only the exit code is glanced at.
#
# Resolving it lazily keeps the public API identical where pyecharts is present
# -- `pybuildingenergy.Graphs_and_report` still works, and still returns the same
# object -- while letting the engine import without it. Anything else the
# charting module exports resolves the same way, which preserves what the old
# `from .source.graphs import *` provided.
_OPTIONAL_MODULES = ("source.graphs",)


def __getattr__(name: str):
    """Resolve names that live in the optional charting modules."""
    if name.startswith("__"):
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    for modname in _OPTIONAL_MODULES:
        try:
            module = importlib.import_module(f".{modname}", __name__)
        except ImportError as exc:
            raise AttributeError(
                f"{__name__}.{name} lives in the optional charting layer "
                f"({modname}), which could not be imported: {exc}. "
                f"Install the charting extras (pyecharts, scipy) to use it; "
                f"they are not needed to run a simulation."
            ) from exc
        if hasattr(module, name):
            value = getattr(module, name)
            globals()[name] = value          # resolve once, then it is a plain attribute
            return value

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "check_heating_system_inputs",
    "HeatingSystemCalculator",
    "EmissionSimulationResult",
    "EmissionSystemCalculator",
    "DistributionSimulationResult",
    "DistributionSystemCalculator",
    "StorageSimulationResult",
    "StorageSystemCalculator",
    "BoilerConfig",
    "BoilerGeneratorCalculator",
    "CoolingSystemSimulationResult",
    "CoolingSystemCalculator",
    "CoolingStorageSimulationResult",
    "CoolingStorageSystemCalculator",
    "CoolingGenerationSimulationResult",
    "CoolingGenerationSystemCalculator",
    "HeatPumpPerformanceDataCalculator",
    "HeatPumpPerformanceDataResult",
    "en14825_part_load_factor",
    "HeatPumpSimulationResult",
    "HeatPumpSystemCalculator",
    "CombustionBoilerSimulationResult",
    "CombustionBoilerSystemCalculator",
    "CogenerationSimulationResult",
    "CogenerationSystemCalculator",
    "DistrictEnergySystemCalculator",
    "DistrictSystemSimulationResult",
    "RenewableEnergySimulationResult",
    "RenewableEnergySystemCalculator",
    "PrimaryEnergyAccountingCalculator",
    "PrimaryEnergyAccountingResult",
    "LightingSimulationResult",
    "LightingSystemCalculator",
    "VentilationSystemCalculator",
    "VentilationSystemSimulationResult",
    "BACSControlFactorCalculator",
    "BACSSimulationResult",
    "CostOptimalityCalculator",
    "EconomicSimulationResult",
    "BiomassBoilerSimulationResult",
    "BiomassBoilerSystemCalculator",
    "ItalianStrepinTables",
    "StrepinCase",
    "apply_extra_measure_specs_to_bui",
    "find_default_workbook",
    "load_italian_strepin_tables",
    "summarize_engine_performance",
    "DHWDesignSimulationResult",
    "DHWDesignLoadCalculator",
    "Volume_and_energy_DHW_calculation",
    "Graphs_and_report",
    "ISO52016",
    "sanitize_and_validate_BUI",
    "HourlyProfileGenerator",
    "get_country_code_from_latlon"
]
