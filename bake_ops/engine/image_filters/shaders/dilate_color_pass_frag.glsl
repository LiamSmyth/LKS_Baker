/* Nearest-valid color dilation (one 4-connected BFS ring).
 * Per-texel via texelFetch + gl_FragCoord: no sampler filtering, so chaining an
 * offscreen color attachment back in as input can never blend across texels.
 * dilateAlpha and fillPhase are push constants (declared by the shader builder). */

void main()
{
    ivec2 sz = textureSize(colorTex, 0);
    ivec2 px = ivec2(gl_FragCoord.xy);

    if (texelFetch(validTex, px, 0).r >= 0.5) {
        fragColor = texelFetch(colorTex, px, 0);
        return;
    }

    if (fillPhase >= 0.5 && texelFetch(footprintTex, px, 0).r < 0.5) {
        fragColor = texelFetch(colorTex, px, 0);
        return;
    }

    /* Neighbour priority must match dilate_cpu BFS tie-breaking so a texel with
     * several valid neighbours copies the same one on both backends. CPU claims
     * a target from its valid neighbour in array scan order
     * (above, left, right, below). The upload flips PNG->GL vertically, so GL
     * +y is array-"above"; order is up, left, right, down. */
    ivec2 offsets[4] = ivec2[4](
        ivec2(0, 1),
        ivec2(-1, 0),
        ivec2(1, 0),
        ivec2(0, -1)
    );

    for (int i = 0; i < 4; i++) {
        ivec2 sp = clamp(px + offsets[i], ivec2(0), sz - ivec2(1));
        if (texelFetch(validTex, sp, 0).r >= 0.5) {
            vec4 src = texelFetch(colorTex, sp, 0);
            if (dilateAlpha >= 0.5) {
                fragColor = src;
            } else {
                vec4 dst = texelFetch(colorTex, px, 0);
                fragColor = vec4(src.rgb, dst.a);
            }
            return;
        }
    }

    fragColor = texelFetch(colorTex, px, 0);
}
