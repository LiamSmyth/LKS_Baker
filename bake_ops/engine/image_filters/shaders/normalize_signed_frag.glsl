void main()
{
    vec2 uv = texCoord_interp;
    float valid = texture(validTex, uv).r;
    if (valid < 0.5) {
        fragColor = vec4(flatFill, flatFill, flatFill, 1.0);
        return;
    }
    float signedVal = texture(imageTex, uv).r;
    float normalized = clamp(signedVal / scale, -1.0, 1.0);
    float gray;
    if (useDirectAmplitude > 0.5) {
        gray = flatFill + normalized * amplitude;
    } else {
        gray = normalized * contrast * 0.5 + flatFill;
    }
    gray = clamp(gray, 0.0, 1.0);
    fragColor = vec4(gray, gray, gray, 1.0);
}
