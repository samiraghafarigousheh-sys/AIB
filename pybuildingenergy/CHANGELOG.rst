Unreleased
----------

* Generalise the ISO 52016-1 §6.5.10 ventilation term to an affine pair
  ``(H_ve, S_ve)`` where ``S_ve = Σ H_k · T_source,k``.  This replaces the
  previous single outdoor-air conductance ``H_ve · T_outdoor`` and supports
  additive airflow streams (infiltration, mechanical supply, purge) at
  independent source temperatures.
* Add ``VentilationStream`` and ``VentilationBoundary`` frozen dataclasses with
  finite-value and non-negative-conductance validation.
* Add ``resolve_ventilation_boundary()`` resolver supporting the existing five
  ``ventilation_type`` configurations (backward-compatible) and an optional
  ``components`` list with per-component operation schedules
  (``component_multipliers``).
* Add ``constant_ach`` component type (explicit infiltration with per-zone
  volume).  Add ``prescribed`` component type for non-outdoor supply streams.
* Convert ``summer_night_purge`` to an additive outdoor-air stream
  (``H_purge = (boost_factor − 1) · H_base``), preserving the previous total
  for all-outdoor configurations.
* Wire ``S_ve`` through all four solver paths (multizone, legacy, causal,
  hybrid), replacing ``H_ve · T_outdoor`` in matrix assembly, ideal-HVAC
  backsolve, and Sankey heat-flow output.
* Add diagnostic outputs ``S_ve_<zone>``, ``T_ve_source_eq_<zone>``, and
  ``Q_ve_<zone>`` (sign convention: positive = heat leaving the zone).
* Fix ``_build_single_zone_building_object_for_core`` to use zone-level
  ``internal_gains`` schedules and ventilation/heating/cooling profiles with
  correct priority over global values.
* Fix ``Temperature_and_Energy_needs_calculation`` and the causal core to treat
  an explicitly passed ``None`` schedule kwarg the same as an absent key, so
  callers such as ``Temperature_and_Energy_needs_calculation_multizone_hybrid``
  do not cause ``generate_category_profile`` to receive ``None``.

0.0.0 (2024-03-26)
------------------

* First release on PyPI.

0.0.6 (2024-04-03)
------------------

* Modify readme.rst file
* Modify Authors.rst

0.0.7 (2024-04-18)
------------------

* Adding calculation of Domestic Hot Water - DHW NEed according to the ISO 12831-3
* Adding example of DHW calculation

2.0.0 (2025-11-19)
------------------

* Adding multizone calculation considering not - thermal adjacent zones
* Adding adiabtic wall calculation for adjacent zone having the same intended use ad the thermal zone
* Adding calculation of natural ventilation using the EN 16798-7
* Adding categories profiles based on the annex of EN 16798-1
* Adding calculation procedure of primary energy using the EN 15316-1
* Reshape the building and havc inputs in a more user-friendly way
* Adding example of multizone calculation

2.0.1 and 2.0.2 (2025-11-24)
------------------
* Update information regarding authors, license, etc.