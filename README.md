# Govee Bluetooth Lights Integration for Home Assistant 🏠

[![GitHub Release](https://img.shields.io/github/v/release/harwoodspike/hass-govee_light_ble?sort=semver&style=for-the-badge&color=green)](https://github.com/harwoodspike/hass-govee_light_ble/releases/)
[![GitHub Release Date](https://img.shields.io/github/release-date/harwoodspike/hass-govee_light_ble?style=for-the-badge&color=green)](https://github.com/harwoodspike/hass-govee_light_ble/releases/)
![GitHub Downloads (all assets, latest release)](https://img.shields.io/github/downloads/harwoodspike/hass-govee_light_ble/latest/total?style=for-the-badge&label=Downloads%20latest%20Release)
![HA Analytics](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fanalytics.home-assistant.io%2Fcustom_integrations.json&query=%24.govee_light_ble.total&style=for-the-badge&label=Active%20Installations&color=red)
![GitHub commit activity](https://img.shields.io/github/commit-activity/m/harwoodspike/hass-govee_light_ble?style=for-the-badge)
[![hacs](https://img.shields.io/badge/HACS-Integration-blue.svg?style=for-the-badge)](https://github.com/hacs/integration)

## Overview

> This integration is still in an experimental stage, please feel free to give feedback :)

The Govee Bluetooth Lights Home Assistant Custom Integration allows you to integrate your Govee bluetooth light (without the cloud!) with your Home Assistant setup.

Changing and retrieving the current state of color, brightness and state is currently supported.

## Installation

### HACS (recommended)

This integration is available in HACS (Home Assistant Community Store).

1. Install HACS if you don't have it already
2. Open HACS in Home Assistant
3. Go to any of the sections (integrations, frontend, automation).
4. Click on the 3 dots in the top right corner.
5. Select "Custom repositories"
6. Add following URL to the repository `https://github.com/harwoodspike/hass-govee_light_ble`.
7. Select Integration as category.
8. Click the "ADD" button
9. Search for "Govee Bluetooth Lights"
10. Click the "Download" button

### Manual

To install this integration manually you have to download [_govee_light_ble.zip_](https://github.com/harwoodspike/hass-govee_light_ble/releases/latest/) and extract its contents to `config/custom_components/govee_light_ble` directory:

```bash
mkdir -p custom_components/govee_light_ble
cd custom_components/govee_light_ble
wget https://github.com/harwoodspike/hass-govee_light_ble/releases/latest/download/govee_light_ble.zip
unzip govee_light_ble.zip
rm govee_light_ble.zip
```

## Configuration

### Using UI

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=govee_light_ble)

From the Home Assistant front page go to `Configuration` and then select `Devices & Services` from the list.
Use the `Add Integration` button in the bottom right to add a new integration called `Govee Bluetooth Lights`.

## Help and Contribution

If you find a problem, feel free to report it and I will do my best to help you.
If you have something to contribute, your help is greatly appreciated!
If you want to add a new feature, add a pull request first so we can discuss the details.

## Disclaimer

This custom integration is not officially endorsed or supported by Govee.
Use it at your own risk and ensure that you comply with all relevant terms of service and privacy policies.
