from common.image_utils import generate_wipe_image
image_bytes = generate_wipe_image("Hello, World!")
if image_bytes is not None and len(image_bytes) > 0:
    print("SUCCESS: generate_wipe_image returned bytes.")
else:
    print("FAILURE: generate_wipe_image did not return bytes.")
