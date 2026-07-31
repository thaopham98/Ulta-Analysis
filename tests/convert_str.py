import re
SIZE_MAP_METRIC = {
    "24 g": ["Glimmer Super Balm"],
    "22 g": ["Marble Cream Blush Stick"],
    "21 g": ["Ultimate Blush Palette"],
    "16.8 g": ["Blushed Duo"],
    "12 g": ["Blursh Pod Domed Blusher"],
    "10 g": ["MegaGlo Blushlighter"],
    "9.5 g": ["VividLuxe Crème Blush Stick"],
    "9 g": ["DreamStick Cream Blush"],
    "8.5 g": ["Cream Stick Blush with Brush Applicator", "Blush Crush Liquid Blush"],
    "8.4 g": ["Effervescence Extra Dimension Face Compact"],
    "8 g": ["Juice Stick Dewy Gel-Cream Blush", "Juice Stick Dewy Gel Blush", "Juice Stick Dewy Sheer Gel Blush"],
    "7.7 g": ["Blushed Liquid Blushlighter"],
    "7.5 g": ["Glow Time Blush Stick", "Teint Idole Shape Stick Creamy Blush Stick"],
    "6 g": [
        "Blushed Cream Blush",
        "Matte Blush",
        "Megaglo Makeup Stick",
        "I'm Blushing 2-in-1 Cheek and Lip Tint",
        "Heart Pressed Powder Blush",
        "Bouncy Pudding Lip & Cheek Tint",
        "Backstage Rosy Glow Stick Radiance and pH-Activated Color Blush Stick",
    ],
    "5.5 g": [
        "Blusher Reloaded",
        "Jelly Blush Stick Lip & Cheek Stain",
        "Baby Got Blush",
        "Bouncy Blur Blush",
    ],
    "5 g": [
        "2-in-1 Mosaic Blush & Bronzer Powder",
        "Liquid Blush - 2-in-1 Lip & Cheek Tint",
        "Strawberry Rococo Series Embossed Blush",
    ],
    "4.5 g": ["Blush-Mallow Soft Blusher", "Skin Silk Marble Blush Stick"],
    "4.3 g": ["Mini VividLuxe Crème Blush Stick"],
    "4.25 g": ["Convertible Color Lip & Cheek Cream Blush"],
    "4 g": ["Color Source Buildable Blush", "Re-tint Blurring Cream Blush"],
    "3.2 g": ["PurePressed Blush"],
    "3 g": ["Magic Touch Cream Blush & Lip Trio", "Just Kissed Lip and Cheek Stain", "Pressed Mineral Blush"],
    "2.5 g": ["Baked Blush"],
    "15 ml": ["Hot Shot Blush Drops", "Tinted Moisturizer Cream Blush"],
    "10.3 ml": ["Unreal Liquid Blush"],
    "10 ml": [
        "Futurist Blushmaker Dewy Cheek Tint Liquid Blush",
        "Superdewy Liquid Blush Burst",
        "Juicy Tubes Cheeks Jelly Blush Tint",
    ],
    "9.5 ml": ["Glimmer Blush Drops"],
    "8.5 ml": ["Skin Idôle Juicy Liquid Blush"],
    "8 ml": ["Maneater Satin Blush Cheek Plump", 
             "Simpsons Collab Saucy Sisters' Fat Cheeks Juicy Liquid Blush - Snarky Scarlet",
             "Simpsons Collab Saucy Sisters' Fat Cheeks Juicy Liquid Blush - Lavender Sass"],
    "7.8 g": ["Macaron Blush & Glow Duo"],
    "6 ml": ["Play Daze Airy Liquid Blush", "Play Daze Airy Soft Matte Liquid Blush"],
    "3.9 ml": ["Jelly Tint - 2-in-1 Lip & Cheek Tint Stain"],
    "3.5 ml": ["Blush Rush Liquid Blush"],
    
}

# drop product_id == "mkt77005996", no longer exist


SIZE_MAP_OZ = {}
# Conversion constants
G_TO_OZ = 28.3495
ML_TO_OZ = 29.5735

for metric_key, values_list in SIZE_MAP_METRIC.items():
    # Use regex to extract the numeric value and the unit, ignoring extra spaces
    match = re.match(r"([\d\.]+)\s*(ml|g)", metric_key.strip().lower())
    
    if match:
        amount = float(match.group(1))
        unit = match.group(2)
        
        # Convert metric to ounces
        if unit == "ml":
            oz_amount = amount / ML_TO_OZ
        elif unit == "g":
            oz_amount = amount / G_TO_OZ
            
        # Format the new key to 1 decimal place (e.g., "1.7 oz")
        # .rstrip('0').rstrip('.') removes trailing zeros if it happens to be a whole number
        formatted_oz = f"{oz_amount:.1f}".rstrip('0').rstrip('.')
        new_key = f"{formatted_oz} oz"
        
        # Initialize the list if the key doesn't exist yet, then extend it
        # (This combines lists if two metric sizes map to the same oz size)
        if new_key not in SIZE_MAP_OZ:
            SIZE_MAP_OZ[new_key] = []
        SIZE_MAP_OZ[new_key].extend(values_list)

print(SIZE_MAP_OZ)