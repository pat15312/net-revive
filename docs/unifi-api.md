# UniFi API verification

The integration was checked against Ubiquiti's official UniFi Network **v10.1.84** API reference on 11 September 2026. The documented OpenAPI specification embedded in the official reference was inspected for paths, payloads and device-port schema. This is a documentation check, not a claim of testing on live switches.

Official references:

- [Getting started with the official UniFi API and local application documentation](https://help.ui.com/hc/en-us/articles/30076656117655-Getting-Started-with-the-Official-UniFi-API)
- [Network API introduction](https://developer.ui.com/network/v10.1.84)
- [Execute Port Action](https://developer.ui.com/network/v10.1.84/executeportaction)
- [Get Adopted Device Details](https://developer.ui.com/network/v10.1.84/getadopteddevicedetails)
- [List Adopted Devices](https://developer.ui.com/network/v10.1.84/listadopteddevices)
- [List Local Sites](https://developer.ui.com/network/v10.1.84/listlocalsites)

## Local endpoints

The API specification uses `/integration` as its server base, with `/v1` paths. UniFi OS consoles additionally route Network requests through `/proxy/network`. These two prefixes are explicit Admin choices; no path is accepted from an ordinary restart client.

| Purpose | Method and suffix below the integration v1 prefix |
| --- | --- |
| Sites | `GET /sites` |
| Adopted devices | `GET /sites/{siteId}/devices` |
| Device and port details | `GET /sites/{siteId}/devices/{deviceId}` |
| Restart one PoE port | `POST /sites/{siteId}/devices/{deviceId}/interfaces/ports/{portIdx}/actions` |

The port-action request body is `{"action":"POWER_CYCLE"}`. Authentication uses the `X-API-Key` header. List endpoints use `offset` and `limit`; NetRevive reads all pages. Device details expose `interfaces.ports[]`, with `idx` identifying the port and the optional `poe` object establishing PoE capability. A present PoE object is meaningful even if its `enabled` value is false. The API's numeric port index is stored as the port identifier and number, scoped to its site and device.

The documented PoE fields include `standard`, `type`, `enabled` and `state`. Port names are not guaranteed by the reference schema; NetRevive uses an optional supplied name and supports administrator labels. Device state must be `ONLINE` at preflight.

## Compatibility and uncertainty

Some UniFi releases or deployment types may not expose these endpoints or allow the desired action with a given key. Connection testing and discovery must succeed before setup completion. An HTTP error is reported to Admin without falling back to undocumented `/api/s/...` commands. Browser code never handles the key or controller requests.

A 2xx response means the API accepted the request. There are no automatic retries for power-cycle POSTs, including timeouts, redirects or server errors. A lost response may follow a successfully delivered command. Unknown acceptance is preserved in detailed history and cooldowns remain active. TLS verification defaults on; redirects and environment HTTP proxies are disabled so credentials stay on the configured local controller path.
