from typing import Dict, List, Union

# https://digital.nhs.uk/developer/api-catalogue/message-exchange-for-social-care-and-health-api#get-/messageexchange/endpointlookup/-ods_code-/-workflow_id-
EndpointLookupItem_v1 = Dict[str, str]
EndpointLookupResponse_v1 = Dict[str, Union[str, List[EndpointLookupItem_v1]]]
EndpointLookupItem_v2 = Dict[str, str]
EndpointLookupResponse_v2 = Dict[str, List[Dict[str, str]]]
# https://digital.nhs.uk/developer/api-catalogue/message-exchange-for-social-care-and-health-api#get-/messageexchange/-mailbox_id-/inbox
ListMessageResponse_v1 = Dict[str, List[str]]
ListMessageResponse_v2 = Dict[str, Union[List[str], Dict[str, str], int]]
CountMessagesResponse_v1 = Dict[str, Union[str, int, bool]]
CountMessagesResponse_v2 = Dict[str, int]
AcknowledgeMessageResponse_v1 = Dict[str, str]
# https://digital.nhs.uk/developer/api-catalogue/message-exchange-for-social-care-and-health-api#get-/messageexchange/-mailbox_id-/outbox/tracking/-local_id-
TrackingResponse_v1 = Dict[str, Union[str, int, bool]]
# https://digital.nhs.uk/developer/api-catalogue/message-exchange-for-social-care-and-health-api#get-/messageexchange/-mailbox_id-/outbox/tracking
TrackingResponse_v2 = Dict[str, Union[str, int, bool]]

# https://digital.nhs.uk/developer/api-catalogue/message-exchange-for-social-care-and-health-api#post-/messageexchange/-mailbox_id-/outbox
SendMessageResponse_v1 = Dict[str, str]
SendMessageResponse_v2 = Dict[str, str]
SendMessageErrorResponse_v1 = Dict[str, str]
