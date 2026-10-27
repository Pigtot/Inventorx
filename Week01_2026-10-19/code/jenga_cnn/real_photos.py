"""Resolve labeled crops by their permanent source URL, never a download's row number."""
import csv


def load_crops(crop_path, credits_path):
    with open(crop_path, newline="", encoding="utf-8") as f:
        picks = list(csv.DictReader(f))
    with open(credits_path, newline="", encoding="utf-8") as f:
        credits = list(csv.DictReader(f))
    by_source = {}
    for row in credits:
        source = row["source"]
        if source in by_source and by_source[source]["file"] != row["file"]:
            raise ValueError(f"More than one downloaded photo has source {source}. Keep one in credits.csv.")
        by_source[source] = row
    for pick in picks:
        source = pick.get("source")
        if not source or source not in by_source:
            raise ValueError(f"Labeled photo {source or pick.get('photo')} is missing from credits.csv. "
                             "Restore that photo and its credits; do not substitute another photo number.")
    return picks, by_source
