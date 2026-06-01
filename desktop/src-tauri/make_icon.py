from PIL import Image, ImageDraw

S = 1024
img = Image.new("RGBA", (S, S), (32, 41, 51, 255))   # slate ink
d = ImageDraw.Draw(img)

# rounded outer frame (paper-white outline)
m = int(S * 0.22)
d.rounded_rectangle([m, m, S - m, S - m], radius=int(S * 0.06),
                    outline=(236, 239, 241, 255), width=int(S * 0.026))

# centered teal block (oklch(58% 0.10 195) ~ teal)
c, r = S * 0.5, S * 0.125
d.rounded_rectangle([c - r, c - r, c + r, c + r], radius=int(S * 0.02),
                    fill=(40, 156, 160, 255))

img.save("icon-source.png")
print("wrote icon-source.png")
