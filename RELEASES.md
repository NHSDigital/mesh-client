Release Notes
=============

These are not all encompassing, but we will try and capture noteable differences here 

----
# 3.0
### v3.0 release includes some significant changes, attempting to capture major differences here


##### - MESH API V2 accept: application/vnd.mesh.v2+json
- Moved to v2 mesh content types, sending `application/vnd.mesh.v2+json` for all requests, and receiving v2 response types
- Allows server to negotiate compression based on accept header.
- All headers will be lower case
- `message.status` are also lower case `accepted`, `acknowledged`, `undeliverable` rather than `Accepted`, `Acknowledged` 


#### Tracking by LocalId removed
- `get_tracking_info` endpoint removed, in favour of track by message_id, as responses are significantly different, use `track_message` endpoint instead


#####  MockMeshApplication removed
- `MockMeshApplication` server removed completely, remaining unique pytests moved from sandbox to pytest-httpserver

#####  Better Typing
- Better defined TypedDicts (>py38) for all expected responses
