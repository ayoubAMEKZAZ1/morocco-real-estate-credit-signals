"""City names as printed in the French bulletins, mapped to English display names."""
CITY_FR_TO_EN = {"Agadir": "Agadir", "Casablanca": "Casablanca", "El Jadida": "El Jadida", "Fès": "Fes",
                 "Kénitra": "Kenitra", "Marrakech": "Marrakech", "Meknès": "Meknes", "Oujda": "Oujda",
                 "Rabat": "Rabat", "Tanger": "Tangier"}


def city_en(name):
    return CITY_FR_TO_EN.get(name.strip(), name.strip())
