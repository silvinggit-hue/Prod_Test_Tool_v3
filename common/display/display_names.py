from __future__ import annotations


DISPLAY_NAME_MAP: dict[str, str] = {
    "NET_RTSPPORT": "RTSP Port",
    "NET_MAC": "MAC Address",
    "NET_LOCALIPMODE": "Local IP Mode",
    "NET_EXTRA_ID": "Extra ID",
    "SYS_VERSION": "Firmware",
    "SYS_MODELNAME": "Model",
    "SYS_MODELNAME_ID": "Model",
    "SYS_MODE": "Type",
    "SYS_BOARDID": "Board ID",
    "SYS_MODULE_TYPE": "Module Type",
    "SYS_MODULE_DETAIL": "Module Detail",
    "SYS_PTZ_TYPE": "PTZ Type",
    "SYS_ZOOMMODULE": "Zoom Module",
    "SYS_PRODUCT_MODEL": "Product Model",
    "SYS_AI_VERSION": "AI Version",
    "SYS_RCV_VERSION": "RCV Version",
    "SYS_CURRENTTIME": "RTC",
    "SYS_STARTTIME": "Start Up Time",
    "SYS_BOARDTEMP": "Temp",
    "SYS_FANSTATUS": "Fan",
    "CAM_READMODULEVERSION": "Module Version",
    "CAM_READMECAVERSION": "PTZ F/W",
    "TEST_Power_CheckString": "Power Type",
    "CDS": "CDS",
    "CURRENT_Y": "Current Y",
    "RATE1": "Rate1",
    "RATE2": "Rate2",
    "RATE3": "Rate3",
    "RATE4": "Rate4",
    "RTC": "RTC",
    "ETHERNET": "Ethernet",
    "TEMP": "Temp",
    "FAN": "Fan",
    "ETHTOOL": "Ethernet Detail",
    "GIS_SENSOR1": "Sensor1",
    "GIS_SENSOR2": "Sensor2",
    "GIS_SENSOR3": "Sensor3",
    "GIS_SENSOR4": "Sensor4",
    "GIS_SENSOR5": "Sensor5",
    "GIS_MOTION1": "Motion1",
    "GIS_MOTION2": "Motion2",
    "GIS_MOTION3": "Motion3",
    "GIS_MOTION4": "Motion4",
    "GIS_VIDEOLOSS1": "VideoLoss1",
    "GIS_VIDEOLOSS2": "VideoLoss2",
    "GIS_VIDEOLOSS3": "VideoLoss3",
    "GIS_VIDEOLOSS4": "VideoLoss4",
    "GIS_ALARM1": "Alarm1",
    "GIS_ALARM2": "Alarm2",
    "GIS_ALARM3": "Alarm3",
    "GIS_ALARM4": "Alarm4",
    "GIS_RECORD1": "Record1",
    "GIS_AIRWIPER": "AirWiper",
    "GRS_AENCBITRATE1": "Audio Enc Bitrate",
    "GRS_ADECBITRATE1": "Audio Dec Bitrate",
    "GRS_ADECALGORITHM1": "Audio Dec Algorithm",
    "GRS_ADECSAMPLERATE1": "Audio Dec Samplerate",
}


def _prettify_fallback(key: str) -> str:
    value = (key or "").strip()
    if not value:
        return "-"
    value = value.replace("_", " ").replace("-", " ").strip()
    parts = [p for p in value.split() if p]
    return " ".join(p.capitalize() for p in parts) if parts else "-"


def display_name(key: str) -> str:
    normalized = (key or "").strip()
    if not normalized:
        return "-"
    return DISPLAY_NAME_MAP.get(normalized, _prettify_fallback(normalized))