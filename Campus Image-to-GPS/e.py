import argparse
import os
from pathlib import Path

import pandas as pd 

from PIL import Image, ExifTags


# Build mapping from EXIF tag id -> name (e.g., 271 -> "Make")
TAGS = ExifTags.TAGS
GPSTAGS = ExifTags.GPSTAGS


def _to_float(x):
    """Convert EXIF rational / int / float to float safely."""
    try:
        
        return float(x)
    except Exception:
        if isinstance(x, tuple) and len(x) == 2 and x[1] != 0:
            return x[0] / x[1]
        return None


def dms_to_decimal(dms, ref):
    """
    Convert EXIF GPS DMS (degrees, minutes, seconds) to decimal degrees.
    dms: tuple of 3 rationals
    ref: 'N','S','E','W'
    """
    if not dms or len(dms) != 3:
        return None

    deg = _to_float(dms[0])
    minutes = _to_float(dms[1])
    seconds = _to_float(dms[2])
    if deg is None or minutes is None or seconds is None:
        return None

    decimal = deg + (minutes / 60.0) + (seconds / 3600.0)
    if ref in ("S", "W"):
        decimal = -decimal
    return decimal


def extract_exif_fields(image_path: Path):
    """
    Returns dict with extracted fields for one image.
    """
    data = {
        "Photo Path": str(image_path),
        "Latitude": None,
        "Longitude": None,
        "Altitude": None,
        "Make/Model": None,
        "Day/Night": "",  
    }

    try:
        with Image.open(image_path) as im:
            exif = im.getexif()
            if not exif:
                return data

            # Make/Model
            make = exif.get(271)  # "Make"
            model = exif.get(272)  # "Model"
            make_str = str(make).strip() if make is not None else ""
            model_str = str(model).strip() if model is not None else ""
            if make_str or model_str:
                data["Make/Model"] = f"{make_str} {model_str}".strip()

            # GPS
            gps_info = None
            # Pillow 10+ stores GPS in a sub-IFD; get_ifd handles it.
            if hasattr(exif, "get_ifd"):
                try:
                    gps_info = exif.get_ifd(34853)  # "GPSInfo"
                except Exception:
                    gps_info = None
            if not gps_info:
                raw_gps = exif.get(34853)
                if isinstance(raw_gps, dict):
                    gps_info = raw_gps
            if not gps_info:
                return data

            # gps_info is a dict: {tag_id: value}
            gps = {}
            for k, v in gps_info.items():
                tag_name = GPSTAGS.get(k, k)
                gps[tag_name] = v

            lat = dms_to_decimal(gps.get("GPSLatitude"), gps.get("GPSLatitudeRef"))
            lon = dms_to_decimal(gps.get("GPSLongitude"), gps.get("GPSLongitudeRef"))
            data["Latitude"] = lat
            data["Longitude"] = lon

            alt = gps.get("GPSAltitude")
            alt_ref = gps.get("GPSAltitudeRef", 0)  # 0=above sea level, 1=below
            alt_val = _to_float(alt)
            if alt_val is not None:
                if alt_ref == 1:
                    alt_val = -alt_val
                data["Altitude"] = alt_val

            return data

    except Exception:
        # If file is corrupted / not readable, keep row but without EXIF
        return data


def main():
    parser = argparse.ArgumentParser(
        description="Extract GPS + phone model from JPG EXIF into CSV/XLSX table."
    )
    parser.add_argument("input_dir", help="Path to folder containing JPG images")
    parser.add_argument(
        "-o",
        "--output",
        default="photos_metadata.csv",
        help="Output file path (.xlsx or .csv). Default: photos_metadata.csv",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    if not input_dir.exists() or not input_dir.is_dir():
        raise SystemExit(f"Input dir not found or not a directory: {input_dir}")

    # Collect JPG/JPEG (case-insensitive)
    # Avoid duplicates on case-insensitive filesystems (e.g., Windows).
    images_map = {}
    for ext in ("*.jpg", "*.JPG", "*.jpeg", "*.JPEG"):
        for p in input_dir.rglob(ext):
            key = os.path.normcase(str(p.resolve()))
            if key not in images_map:
                images_map[key] = p
    images = list(images_map.values())

    rows = [extract_exif_fields(p) for p in sorted(images)]

    df = pd.DataFrame(rows, columns=[
        "Photo Path",
        "Latitude",
        "Longitude",
        "Altitude",
        "Make/Model",
        "Day/Night",
    ])

    out_path = Path(args.output)
    out_ext = out_path.suffix.lower()

    if out_ext == ".csv":
        df.to_csv(out_path, index=False, encoding="utf-8-sig")
        print(f"Saved CSV: {out_path.resolve()}")
    elif out_ext == ".xlsx":
        df.to_excel(out_path, index=False)
        print(f"Saved XLSX: {out_path.resolve()}")
    else:
        # Default: save CSV if user gave no/unknown extension
        out_path = out_path.with_suffix(".csv")
        df.to_csv(out_path, index=False, encoding="utf-8-sig")
        print(f"Saved CSV: {out_path.resolve()}")


if __name__ == "__main__":
    main()


