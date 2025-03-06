from typing import Literal, Optional, TypedDict

# https://digital.nhs.uk/developer/api-catalogue/message-exchange-for-social-care-and-health-api#get-/messageexchange/endpointlookup/-ods_code-/-workflow_id-


class EndpointLookupItem_v1(TypedDict):
    address: str
    description: Optional[str]
    endpoint_type: Literal["MESH"]


class EndpointLookupResponse_v1(TypedDict):
    query_id: str
    results: list[EndpointLookupItem_v1]


class EndpointLookupItem_v2(TypedDict):
    mailbox_id: str
    mailbox_name: Optional[str]


class EndpointLookupResponse_v2(TypedDict):
    results: list[EndpointLookupItem_v2]


# https://digital.nhs.uk/developer/api-catalogue/message-exchange-for-social-care-and-health-api#get-/messageexchange/-mailbox_id-/inbox
class ListMessageResponse_v1(TypedDict):
    messages: list[str]


class ListMessageResponse_v2(TypedDict):
    messages: list[str]
    links: dict[Literal["self", "next"], str]
    approx_inbox_count: int


class CountMessagesResponse_v1(TypedDict):
    count: int
    internalID: str
    allResultsIncluded: bool


class CountMessagesResponse_v2(TypedDict):
    count: int


class AcknowledgeMessageResponse_v1(TypedDict):
    messageId: str


# https://digital.nhs.uk/developer/api-catalogue/message-exchange-for-social-care-and-health-api#get-/messageexchange/-mailbox_id-/outbox/tracking/-local_id-
class TrackingResponse_v1(TypedDict):
    addressType: Optional[str]
    checksum: Optional[str]
    chunkCount: Optional[int]
    compressFlag: Optional[str]
    contentEncoding: Optional[str]
    downloadTimestamp: Optional[str]
    dtsId: str
    encryptedFlag: Optional[str]
    expiryTime: Optional[str]
    failureDate: Optional[str]
    failureDiagnostic: Optional[str]
    fileName: Optional[str]
    fileSize: int

    isCompressed: Optional[str]
    linkedMsgId: Optional[str]
    localId: Optional[str]
    meshRecipientOdsCode: Optional[str]
    messageId: str
    messageType: Optional[str]
    partnerId: Optional[str]

    recipient: Optional[str]
    recipientName: Optional[str]
    recipientOrgCode: Optional[str]
    recipientOrgName: Optional[str]
    recipientSmtp: Optional[str]

    sender: Optional[str]
    senderName: Optional[str]
    senderOdsCode: Optional[str]
    senderOrgCode: Optional[str]
    senderOrgName: Optional[str]
    senderSmtp: Optional[str]

    status: Optional[str]

    statusCode: Optional[str]
    statusDescription: Optional[str]


# https://digital.nhs.uk/developer/api-catalogue/message-exchange-for-social-care-and-health-api#get-/messageexchange/-mailbox_id-/outbox/tracking
class TrackingResponse_v2(TypedDict):
    message_id: str
    local_id: Optional[str]
    workflow_id: Optional[str]
    filename: Optional[str]

    expiry_time: Optional[str]
    upload_timestamp: Optional[str]

    recipient: Optional[str]
    recipient_name: Optional[str]
    recipient_ods_code: Optional[str]
    recipient_org_code: Optional[str]
    recipient_org_name: Optional[str]

    status_success: Optional[bool]
    status: Optional[str]
    status_event: Optional[str]
    status_timestamp: Optional[str]
    status_description: Optional[str]
    status_code: Optional[str]


# https://digital.nhs.uk/developer/api-catalogue/message-exchange-for-social-care-and-health-api#post-/messageexchange/-mailbox_id-/outbox
class SendMessageResponse_v1(TypedDict):
    messageID: str


class SendMessageResponse_v2(TypedDict):
    message_id: str


class SendMessageErrorResponse_v1(TypedDict):
    messageID: Optional[str]
    errorEvent: Optional[str]
    errorCode: Optional[str]
    errorDescription: Optional[str]


class SendMessageErrorResponse_v2(TypedDict):
    message_id: Optional[str]
    internal_id: Optional[str]
    detail: list[dict]
