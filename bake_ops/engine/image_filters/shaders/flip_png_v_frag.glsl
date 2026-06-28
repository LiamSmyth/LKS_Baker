void main()
{
    vec2 uv = texCoord_interp;
    vec2 flipped = vec2(uv.x, 1.0 - uv.y);
    fragColor = texture(imageTex, flipped);
}
