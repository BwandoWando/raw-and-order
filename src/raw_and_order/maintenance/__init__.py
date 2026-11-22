"""One-off upkeep commands over photos already in the database.

They fix stored data after the app changes, without processing photos
again and without calling the LLM:

- :mod:`~raw_and_order.maintenance.exif_reread`: read EXIF again
  (``raw-and-order process FOLDER --reread-exif``).
- :mod:`~raw_and_order.maintenance.rehash`: recompute perceptual hashes
  (``raw-and-order rehash``).

Both visit stored photos (the EXIF re-read only those under FOLDER), update
only what changed, and report the outcome as a
:class:`~raw_and_order.maintenance.report.MaintenanceSummary`.
"""
