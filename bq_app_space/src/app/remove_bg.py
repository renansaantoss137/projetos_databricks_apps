from PIL import Image

def process_full_transparent_logo(input_path, output_path, threshold=225):
    img = Image.open(input_path).convert('RGBA')
    width, height = img.size
    
    datas = img.load()
    for y in range(height):
        for x in range(width):
            r, g, b, a = datas[x, y]
            if r >= threshold and g >= threshold and b >= threshold:
                min_val = min(r, g, b)
                if min_val >= threshold:
                    avg_val = (r + g + b) / 3.0
                    alpha = int(max(0, (255 - avg_val) / (255 - threshold) * 255))
                    datas[x, y] = (r, g, b, alpha)
    
    bbox = img.getbbox()
    if bbox:
        img_cropped = img.crop(bbox)
        img_cropped.save(output_path, 'PNG')
        print(f"Successfully saved full transparent logo (symbol + text) to {output_path}")

if __name__ == '__main__':
    process_full_transparent_logo('static/images/tradego_card.png', 'static/images/tradego_transparent.png')
