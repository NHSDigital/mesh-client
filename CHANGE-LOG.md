Release Notes
=============

These are not all encompassing, but we will try and capture noteable differences here.

----
# 3.1
* expose a `send_chunk` method which will return the bare http response, but will still take care of some of the messier header negotiation
* support for alternative names for optional send headers
* removed `mex-MessageType` as a send header, it's not required
* removed `mex-From` as sender header, it's not required
* support for setting `compress` for an individual message (rather than just using the 'transparent_compress' init arg)

# 3.0
### v3.0 release includes some significant changes, attempting to capture major differences here

##### - MESH API V2 accept: application/vnd.mesh.v2+json
- Moved to v2 mesh content types, sending `application/vnd.mesh.v2+json` for all requests, and receiving v2 response types.
- Allows server to negotiate compression based on accept header.
- For chunked messages, all chunks except the last chunk, should be greater than `5MB` in size, though this is not enforced in the client or mesh sandbox to allow testing.
- All headers will be lowercase.
- Inbox pagination and filtering `list_messages` supports `max_results` and `workflow_filter` passthrough.
- new method `iterate_message_ids`, supporting  workflow_filter
- new method `iterate_messages`, supporting  workflow_filter
- `message.status` are also lower case `accepted`, `acknowledged`, `undeliverable` rather than `Accepted`, `Acknowledged`. 

##### - Default Retries
- previously `send_chunk` retries could be optionally enabled by setting the `max_chunk_retries` when creating the client object this has been replaced with the `MeshRetry` based on the standard `urlib3.Retry` object in the HTTPAdapter
- By default, requests will have two retries with an exponential backoff of `500ms`, but initial `send_message` requests will not be retried.
- If you wish to disable retries completely set `max_retries=0`
- Timings and specific behaviour can be tuned using `retry_backoff_factor`, `retry_status_force_list` and `retry_methods` or completely overriden by passing in `max_retries=Retry(...)`
- NOTE: if retries are enabled, HTTPErrors will be wrapped in `request.exceptions.RetryError`, ensure catching RetryError as per HTTPError

#### - ENDPOINT changes
- HSCN endpoints are 'deprecated', and internet facing endpoints should be used in preference. For clarity HSCN endpoints have been renamed, prefixed `DEPRECATED_HSCN_`.
- Primary endpoints are now `LIVE_ENDPOINT`, `INT_ENDPOINT`, `DEP_ENDPOINT`.
- `TRAIN`, `OPENTEST`, `DEV` endpoints have been removed, but will still work with the client if you have the url and certificate.


#### - Tracking
- `get_tracking_info` and `track_by_message_id` endpoints removed, in favour `track_message` as v2 api tracking response is significantly different.

##### - MockMeshApplication removed
- `MockMeshApplication` server removed completely, remaining unique pytests moved from sandbox to pytest-httpserver.

##### - Better Typing
- Better defined TypedDicts (>py38) for all expected responses.
