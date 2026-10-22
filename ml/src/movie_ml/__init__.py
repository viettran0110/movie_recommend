"""Offline recommendation code (ADR-026).

A pure library: functions take arrays or plain records and return results. It never imports
the API app, reads settings, or touches the database. Worker tasks in apps/api load data,
call into this package, and write the results back.
"""
