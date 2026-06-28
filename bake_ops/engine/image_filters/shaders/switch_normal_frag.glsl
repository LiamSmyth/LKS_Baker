void main()
{
    vec4 color = texture(imageTex, texCoord_interp);
    if (flipGreen > 0.5) {
        color.g = 1.0 - color.g;
    }
    fragColor = color;
}
