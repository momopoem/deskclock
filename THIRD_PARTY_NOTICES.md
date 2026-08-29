# Third-Party Notices

The MIT License in `LICENSE` applies to the original Desk Side Clock
software. It does not replace the licenses of the third-party assets and
services listed below.

## DSEG font

`fonts/DSEG7Classic-Bold.ttf` is part of the DSEG Font Family by keshikan.

- Copyright (c) 2020, keshikan (https://www.keshikan.net/)
- Reserved Font Name: "DSEG"
- License: SIL Open Font License 1.1
- License text: `fonts/DSEG-LICENSE.txt`
- Upstream: https://github.com/keshikan/DSEG

## Weather Icons font

`fonts/weathericons/weathericons-regular-webfont.ttf` is from Weather Icons.
The original icon designs are by Lukas Bischoff; the project and later icon
art are maintained by Erik Flowers.

- Font license: SIL Open Font License 1.1
- License text: `fonts/weathericons/LICENSE.txt`
- Upstream: https://github.com/erikflowers/weather-icons

No bundled font file has been modified. Modified font versions must continue
to comply with the SIL Open Font License, including Reserved Font Name rules
where applicable.

## Open-Meteo

Weather data obtained from Open-Meteo is licensed under Creative Commons
Attribution 4.0 International (CC BY 4.0). Attribution:

> Weather data by Open-Meteo.com (CC BY 4.0)

- Terms: https://open-meteo.com/en/terms
- Data license: https://creativecommons.org/licenses/by/4.0/

The default `api.open-meteo.com` free API endpoint is offered for
non-commercial use and is subject to Open-Meteo's current rate limits and
terms. Commercial deployments must use an appropriate paid or self-hosted
endpoint and set `OPEN_METEO_BASE_URL` accordingly.

## Python and operating-system dependencies

Packages listed in `requirements.txt`, as well as system packages loaded at
runtime, retain their own upstream licenses. They are not relicensed by this
repository's MIT License.
