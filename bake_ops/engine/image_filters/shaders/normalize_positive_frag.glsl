void main()
{
    vec2 uv = texCoord_interp;
    float valid = texture(validTex, uv).r;
    if (valid < 0.5) {
        fragColor = vec4(flatFill, flatFill, flatFill, 1.0);
        return;
    }
    float value = texture(imageTex, uv).r;
    float gray = clamp(value / scale, 0.0, 1.0);
    fragColor = vec4(gray, gray, gray, 1.0);
}
