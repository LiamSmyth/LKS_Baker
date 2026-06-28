/* Grow the binary valid mask by one 4-connected ring.
 * Per-texel via texelFetch: the mask is a hard 0/1 field, so filtered sampling
 * (which yields 0.5 at edges) must never be used when chaining this pass. */
void main()
{
    ivec2 sz = textureSize(validTex, 0);
    ivec2 px = ivec2(gl_FragCoord.xy);

    if (texelFetch(validTex, px, 0).r >= 0.5) {
        fragColor = vec4(1.0, 0.0, 0.0, 1.0);
        return;
    }

    if (fillPhase >= 0.5 && texelFetch(footprintTex, px, 0).r < 0.5) {
        fragColor = vec4(0.0, 0.0, 0.0, 1.0);
        return;
    }

    ivec2 offsets[4] = ivec2[4](
        ivec2(-1, 0),
        ivec2(1, 0),
        ivec2(0, -1),
        ivec2(0, 1)
    );

    for (int i = 0; i < 4; i++) {
        ivec2 sp = clamp(px + offsets[i], ivec2(0), sz - ivec2(1));
        if (texelFetch(validTex, sp, 0).r >= 0.5) {
            fragColor = vec4(1.0, 0.0, 0.0, 1.0);
            return;
        }
    }

    fragColor = vec4(0.0, 0.0, 0.0, 1.0);
}
