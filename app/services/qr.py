import io
import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers.pil import RoundedModuleDrawer
from qrcode.image.styles.colormasks import RadialGradiantColorMask

def generate_qr_code_bytes(url: str) -> bytes:
    """
    Generate a QR code pointing to the given URL and return its bytes.
    Generates a beautifully designed QR code instead of the standard black and white.
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)

    # Create a styled QR code (dark purple/blue theme with rounded module corners)
    # This aligns with the "vibrant colors / premium design" requirements!
    img = qr.make_image(
        image_factory=StyledPilImage,
        module_drawer=RoundedModuleDrawer(),
        color_mask=RadialGradiantColorMask(
            back_color=(255, 255, 255),  # White background
            center_color=(99, 102, 241),  # Indigo center
            edge_color=(49, 46, 129)      # Dark Navy edges
        )
    )
    
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
