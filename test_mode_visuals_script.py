import mode_visuals
from PIL import ImageDraw, Image
from mode_visuals import TextRenderConfig

# Create a dummy image and draw context
img = Image.new('RGB', (100, 100), color = 'red')
draw = ImageDraw.Draw(img)

# Create a test render config
config = TextRenderConfig(
    font_path='font1.ttf', # Dummy path, _find_best_font_size catches exception and uses default
    max_width=50,
    max_height=50,
    max_font_size=20,
    text_align='center'
)

font, text = mode_visuals._find_best_font_size(draw, "Hello World", config)
print(f"Text wrapped: {repr(text)}")
print("Successfully called _find_best_font_size")
