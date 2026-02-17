from google.cloud import vision


def google_ocr_bytes(image_bytes: bytes) -> str:
    client = vision.ImageAnnotatorClient()

    image = vision.Image(content=image_bytes)

    response = client.document_text_detection(image=image)

    if response.error.message:
        raise RuntimeError(response.error.message)

    if response.full_text_annotation:
        return response.full_text_annotation.text or ""

    if response.text_annotations:
        return response.text_annotations[0].description or ""

    return ""