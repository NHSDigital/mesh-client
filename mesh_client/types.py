from typing import Literal, TypedDict

# https://digital.nhs.uk/developer/api-catalogue/message-exchange-for-social-care-and-health-api#get-/messageexchange/endpointlookup/-ods_code-/-workflow_id-


class EndpointLookupItem_v1(TypedDict):
    address: str
    description: str | None
    endpoint_type: Literal["MESH"]


class EndpointLookupResponse_v1(TypedDict):
    query_id: str
    results: list[EndpointLookupItem_v1]


class EndpointLookupItem_v2(TypedDict):
    mailbox_id: str
    mailbox_name: str | None


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
    addressType: str | None
    checksum: str | None
    chunkCount: int | None
    compressFlag: str | None
    contentEncoding: str | None
    downloadTimestamp: str | None
    dtsId: str
    encryptedFlag: str | None
    expiryTime: str | None
    failureDate: str | None
    failureDiagnostic: str | None
    fileName: str | None
    fileSize: int

    isCompressed: str | None
    linkedMsgId: str | None
    localId: str | None
    meshRecipientOdsCode: str | None
    messageId: str
    messageType: str | None
    partnerId: str | None

    recipient: str | None
    recipientName: str | None
    recipientOrgCode: str | None
    recipientOrgName: str | None
    recipientSmtp: str | None

    sender: str | None
    senderName: str | None
    senderOdsCode: str | None
    senderOrgCode: str | None
    senderOrgName: str | None
    senderSmtp: str | None

    status: str | None

    statusCode: str | None
    statusDescription: str | None


# https://digital.nhs.uk/developer/api-catalogue/message-exchange-for-social-care-and-health-api#get-/messageexchange/-mailbox_id-/outbox/tracking
class TrackingResponse_v2(TypedDict):
    message_id: str
    local_id: str | None
    workflow_id: str | None
    filename: str | None

    expiry_time: str | None
    upload_timestamp: str | None

    recipient: str | None
    recipient_name: str | None
    recipient_ods_code: str | None
    recipient_org_code: str | None
    recipient_org_name: str | None

    status_success: bool | None
    status: str | None
    status_event: str | None
    status_timestamp: str | None
    status_description: str | None
    status_code: str | None


# https://digital.nhs.uk/developer/api-catalogue/message-exchange-for-social-care-and-health-api#post-/messageexchange/-mailbox_id-/outbox
class SendMessageResponse_v1(TypedDict):
    messageID: str


class SendMessageResponse_v2(TypedDict):
    message_id: str


class SendMessageErrorResponse_v1(TypedDict):
    messageID: str | None
    errorEvent: str | None
    errorCode: str | None
    errorDescription: str | None


class SendMessageErrorResponse_v2(TypedDict):
    message_id: str | None
    internal_id: str | None
    detail: list[dict]
