# config_manager.py

import configparser
import os

CONFIG_FILE = 'config.ini'
# Заранее определим список API, которые мы планируем поддерживать.
# Это позволит GUI динамически создавать поля для них.
SUPPORTED_APIS = ['mouser', 'digikey', 'farnell', 'lcsc']


def load_api_keys():
    """
    Загружает все API ключи из config.ini.
    Возвращает словарь вида {'mouser': 'key1', 'digikey': 'key2', ...}.
    """
    keys = {}
    if not os.path.exists(CONFIG_FILE):
        return keys

    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)

    for api_name in SUPPORTED_APIS:
        if config.has_section(api_name):
            # Используем .get() с запасным вариантом None на случай, если ключ пуст
            keys[api_name] = config[api_name].get('api_key', None)

    return keys


def save_api_keys(api_keys):
    """
    Сохраняет словарь с API ключами в config.ini.
    Пустые ключи не сохраняются.
    """
    config = configparser.ConfigParser()
    for api_name, key in api_keys.items():
        if key:  # Сохраняем секцию, только если ключ не пустой
            config[api_name] = {'api_key': key}

    with open(CONFIG_FILE, 'w') as configfile:
        config.write(configfile)