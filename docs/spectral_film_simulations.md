# Spectral film simulations from scratch

> **来源**: [https://discuss.pixls.us/t/48209](https://discuss.pixls.us/t/48209)
> **帖子数**: 710 | **浏览量**: 30676
> **抓取时间**: 2026-05-15 05:37

---


---

## #1 **Andrea** (@arctic) · 2025-02-09 19:35

> **TL;DR**
>
> I’m exploring simulations of the full-analog color photography process (negative + print) using only published datasheets and basic principles. The goal is to recreate signature looks from Kodak and Fujifilm using a physically based model (with spectral calculations, grain, couplers, halation, etc.) that offers tunability beyond standard LUTs. More details and code are available on GitHub ([agx-emulsion](https://github.com/andreavolpato/agx-emulsion)); all results here are with [v0.1.0](https://github.com/andreavolpato/agx-emulsion/releases/tag/v0.1.0-alpha) that is a bit old, have a look to the improvements in the `main` branch.

# [](#p-356352-the-true-color-of-film-negatives-1)The true color of film negatives

A while back, I came across an online discussion about the “real colors of film negatives”. Although I can’t recall the exact source, the key takeaway was that the final colors depend heavily on the second stage of the imaging process, whether it’s the scanner’s color processing or the analog RA4 color reversal printing process. Analog printing seemed like the most authentic way to define the look, especially since companies (primarily Kodak) spent decades refining it.

This idea led me to explore simulating the full analog pipeline of color photography. I am clearly not an expert in darkroom techniques or color science, and initially, I grossly underestimated the challenge. Luckily, I found a few nice book chapters [1,2,3]. Film emulsions are quite sophisticated, relying on finely tuned chemistry with silver halides, several dye couplers, and a pinch of magic. As a trained chemist I have a deep admiration for all the science and engineering needed to make film. For anyone interested in film manufacturing, I highly recommend checking out the series of videos by SmarterEveryDay on Kodak ( [How Does Kodak Make Film?](https://www.youtube.com/watch?v=HQKy1KJpSVc) series of 3, [The Chemistry of Kodak Film](https://www.youtube.com/watch?v=zJ8aNPStQ8M), [Kodak’s Film Quality Control Process](https://www.youtube.com/watch?v=VIH0dEMyv9w)).

## [](#p-356352-goal-and-motivation-2)Goal and motivation

My goal is to simulate the entire analog photographic process, from film capture to the final print, using only the datasheets and basic knowledge. I would like to capture the look of products from Kodak and Fujifilm starting from publicly available spectroscopic data. For example, Portra film and its matching paper are designed to deliver subtle hue shifts and perfect contrast for skin tones, while consumer films and paper are more saturated and versatile. How much of these characteristics can we recreate from scratch?

While film simulation LUTs share similar goals, they often lack the flexibility to be fine-tuned. In contrast, a fully physically based pipeline can better reproduce the real-world versatility of the negative plus RA4 printing process by offering adjustable parameters to tailor the final look. Naturally, this approach also brings along the inherent limitations of analog photography, so you need to appreciate (or be nostalgic for) the analog process to embrace these constraints.

## [](#p-356352-negative-and-print-exposure-3)Negative and print exposure

Here are some test-strips to introduce the capability of the simulation. The overall imaging process is split in two steps: negative and print. Two different exposures can be controlled, and color filters in the enlarger can balance the colors of the print. Here are virtual scans of Kodak Gold 200 at different exposure compensations of the negative.

[[![two_uncles_negative_exposure_ramp_gold_200_crystal_archive](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/e/ae8cef80194d9b42dee6698530f25c0f747e7443_2_690x517.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/e/ae8cef80194d9b42dee6698530f25c0f747e7443_2_690x517.png)

two_uncles_negative_exposure_ramp_gold_200_crystal_archive1920×1440 1.23 MB](/uploads/short-url/oU922nJGUM66nS3ow8h2knX2s0j.png?dl=1)

The following strips are virtual prints on Fujifilm Crystal Archive TypeII at different print exposures (and constant good negative exposure).

[[![two_uncles_print_exposure_ramp_gold_200_crystal_archive](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/3/135d60cb67ad1b429cf0e85dce629389ced623e1_2_690x517.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/3/135d60cb67ad1b429cf0e85dce629389ced623e1_2_690x517.png)

two_uncles_print_exposure_ramp_gold_200_crystal_archive1920×1440 1.71 MB](/uploads/short-url/2Lj8hzlLBUbVQAfl4YTfVgO07N7.png?dl=1)

Raw file taken from this Play Raw [Two Taiwanese uncles playing chess](https://discuss.pixls.us/t/two-taiwanese-uncles-playing-chess/47116), thank you [@streetfighter](/u/streetfighter).

## [](#p-356352-the-challenge-of-using-datasheets-4)The challenge of using datasheets

Published data are measured with densitometers, RGB or diffuse, and they need to be unmixed to refer to the density developed in each channel independently. I could go deeper in what I am doing if anyone is interested. It is not very complex, but I should write down some formalism and math. Most of the times data is not self consistent after “the unmixing” and I need to apply some reasonable corrections. I am assuming that the film should be able to reproduce a neutral-ish 18% gray when printed, even when under- or overexposed, at constant enlarger filter values. So far, Kodak data mostly behaves well by default, while Fujifilm data is trickier and often requires additional corrections.

Here are examples of virtual prints of neutral gradients shot at different exposures and compensated in the virtual printing process to produce roughly the same exposure First let’s analyze Kodak Portra 400, without corrections and after the unmixing. It looks neutral as it should, just a touch of warmer tones when overexposed.

[[![gradient_exposure_ramp_portra_400_no_corrections_portra_endura](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/8/1807f6aec89f4813566acbda1bf9a6fa953a14cd_2_690x517.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/8/1807f6aec89f4813566acbda1bf9a6fa953a14cd_2_690x517.png)

gradient_exposure_ramp_portra_400_no_corrections_portra_endura1920×1440 587 KB](/uploads/short-url/3qAwjCP6888WOzUZorvQTWZbM8B.png?dl=1)

Below is Fujifilm Pro 400h after the unmixing. It has strong hue shifts and it is not really usable in this state. Maybe additional calibrations are needed but not specified in the datasheet?

[[![gradient_exposure_ramp_pro_400h_uncorrected_portra_endura](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/8/1859e6b2aae15692fa2a93466cc3c304c55b9d72_2_690x517.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/8/1859e6b2aae15692fa2a93466cc3c304c55b9d72_2_690x517.png)

gradient_exposure_ramp_pro_400h_uncorrected_portra_endura1920×1440 566 KB](/uploads/short-url/3tq4rpciFg6ZkvgGtfWqdcyMbbY.png?dl=1)

After correction of the density characteristic curves, the gradient at base exposure is quite neutral. Still small shifts are visible at extreme over/under exposure.

[[![gradient_exposure_ramp_pro_400h_portra_endura](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/d/3d653bfcf994d37b5cb355527f5fc087bcb23070_2_690x517.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/d/3d653bfcf994d37b5cb355527f5fc087bcb23070_2_690x517.png)

gradient_exposure_ramp_pro_400h_portra_endura1920×1440 581 KB](/uploads/short-url/8L81bZ0Hm2qB1A7mJzORpUkCp9e.png?dl=1)

# [](#p-356352-preliminary-results-5)Preliminary results

Since analog film is designed to work well on skin tones and nature-greenery, I picked some colorful portraits from [100% Free Raw Photos - Download Raw Files For Editing Now](http://signatureedits.com/free-raw-photos) for showcase (file names of the “default” darktable images have full credits).

### [](#p-356352-kodak-portra-400-vs-fujifilm-pro-400h-6)Kodak Portra 400 vs Fujifilm Pro 400h

[[![Signature Edits Free Raw Files - Tag @signatureeditsco IMG_0913](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/2/52ddb2fc96f5109343071d68a322f6814a9ee4da_2_222x333.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/2/52ddb2fc96f5109343071d68a322f6814a9ee4da_2_222x333.jpeg)

Signature Edits Free Raw Files - Tag @signatureeditsco IMG_09131334×2000 990 KB](/uploads/short-url/bP48JqHX6UOvaboxaMLnWz7TZLI.jpeg?dl=1)

[[![leaves_portra_400_portra_endura_11cpl_-4y7m_0.9pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/7/0733e7e0be5f0c17d064338b473933ef6344c026_2_222x333.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/7/0733e7e0be5f0c17d064338b473933ef6344c026_2_222x333.png)

leaves_portra_400_portra_endura_11cpl_-4y7m_0.9pe1334×2000 4.34 MB](/uploads/short-url/11Iy5OlaxZc4Qsjxg10MVzsA9z8.png?dl=1)

[[![leaves_pro_400h_portra_endura_10cpl_-4y7m_0.9pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/5/f52a4fe7f32be668584e1c2b24133c22f688ee4d_2_222x333.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/5/f52a4fe7f32be668584e1c2b24133c22f688ee4d_2_222x333.png)

leaves_pro_400h_portra_endura_10cpl_-4y7m_0.9pe1334×2000 4.3 MB](/uploads/short-url/yYPDhvvqh0NFaUAbKxo0gu4Ffk1.png?dl=1)

From left to right:

(i) image exported with darktable using sigmoid with contrast set to 2, [xmp](/uploads/short-url/6PCT0ha8KVerrZztMR8gbeeiqz1.xmp) (13.7 KB)

(ii) Kodak Portra 400 and Kodak Portra Endura print paper

(iii) Fujifilm Pro 400h and Kodak Portra Endura print paper

Some settings: -4Y and 7M enlarger filter, 0.9 print exposure. The input of the simulation is a 16bit PNG from darktable with the same settings as the XMP file, but with sigmoid deactivated and exposure reduced to avoid clipping.

Overall Pro 400h seems to have cooler greens and a little more contrast than Portra 400.

[[![Detty Studio](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/3/a34dc3ff7a1f2d0bbfb7fda664ed9f7809f148e7_2_222x333.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/3/a34dc3ff7a1f2d0bbfb7fda664ed9f7809f148e7_2_222x333.jpeg)

Detty Studio1333×2000 1.68 MB](/uploads/short-url/niErgoyKew0e5IAxdsMNY7WmTiv.jpeg?dl=1)

[[![reds_portra_400_portra_endura_11cpl_-3y15m_1p4pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/a/1afab84ce9d2ee92edd633d45ce393c83580cee8_2_222x333.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/a/1afab84ce9d2ee92edd633d45ce393c83580cee8_2_222x333.png)

reds_portra_400_portra_endura_11cpl_-3y15m_1p4pe1333×2000 4.17 MB](/uploads/short-url/3QFzUpldHC6aJzcfNF2gjUkHWm4.png?dl=1)

[[![reds_pro_400h_portra_endura_10cpl_0y7m_1p4pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/8/e8b9b06d04e4e0de6447695dc2b2510547c5357c_2_222x333.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/8/e8b9b06d04e4e0de6447695dc2b2510547c5357c_2_222x333.png)

reds_pro_400h_portra_endura_10cpl_0y7m_1p4pe1333×2000 4.11 MB](/uploads/short-url/xcMBQ9D1nNGmwinnnATWdH5uMeo.png?dl=1)

From left to right:

(i) image exported with darktable using sigmoid with contrast set to 2, [xmp](/uploads/short-url/mF4v4vAsLCSWvKM0rsGInGoS7AJ.xmp) (9.7 KB)

(ii) Kodak Portra 400 and Kodak Portra Endura print paper

(iii) Fujifilm Pro 400h and Kodak Portra Endura print paper

Some settings: -3Y and 15M enlarger filter for Portra 400, and 0Y -7M for Pro 400h, 1.4 print exposure.

[[![credit @signatureeditsco - signatureedits.com _MG_3186](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/d/4df02027342fea8db43567803c4918b944ae6c82_2_222x333.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/d/4df02027342fea8db43567803c4918b944ae6c82_2_222x333.jpeg)

credit @signatureeditsco - signatureedits.com _MG_31861333×2000 1.68 MB](/uploads/short-url/b7tenBevQffeaphozq3BBpoNTRU.jpeg?dl=1)

[[![blues_portra_400_portra_endura_11cpl_-6y10m_1pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/b/fb51facdbb8f5dd47bb0d08732e169156f4652d8_2_222x333.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/b/fb51facdbb8f5dd47bb0d08732e169156f4652d8_2_222x333.png)

blues_portra_400_portra_endura_11cpl_-6y10m_1pe1332×2000 4.31 MB](/uploads/short-url/zRhu7lQ4fQD8oNSwnL4gLIq70Ok.png?dl=1)

[[![blues_pro_400h_portra_endura_10cpl_-6y10m_1pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/4/7469a5d3b9e4ba53e1ba6a3ade9c400f25be356c_2_222x333.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/4/7469a5d3b9e4ba53e1ba6a3ade9c400f25be356c_2_222x333.png)

blues_pro_400h_portra_endura_10cpl_-6y10m_1pe1332×2000 4.24 MB](/uploads/short-url/gBPJCDASt4l5EmymTpsygbRiyao.png?dl=1)

From left to right:

(i) image exported with darktable using sigmoid with contrast set to 2, [xmp](/uploads/short-url/75o1ToNGhPeN57XHMmqE8z0bt5p.xmp) (9.6 KB)

(ii) Kodak Portra 400 and Kodak Portra Endura print paper

(iii) Fujifilm Pro 400h and Kodak Portra Endura print paper

Some settings: -6Y and 10M enlarger filter, 1.0 print exposure.

Blue colors in Pro 400h have a cooler tone when compared with Portra 400.

<details>
<summary>
Color checker comparisons (Kodak Portra 400 vs Fujifilm Pro 400h)</summary>

[[![cc2005_kodak_portra_400_auc_kodak_portra_endura_uc](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/8/381c3967edfcdda21424ba9718c9cea2a155f51f_2_690x492.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/8/381c3967edfcdda21424ba9718c9cea2a155f51f_2_690x492.png)

cc2005_kodak_portra_400_auc_kodak_portra_endura_uc2100×1500 136 KB](/uploads/short-url/80ncVuz3v4mY7tOoekczakrZwKP.png?dl=1)

[[![cc2005_fujifilm_pro_400h_auc_kodak_portra_endura_uc](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/6/f6f02dadde665994a5164d2d54ff4af37a21664b_2_690x492.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/6/f6f02dadde665994a5164d2d54ff4af37a21664b_2_690x492.png)

cc2005_fujifilm_pro_400h_auc_kodak_portra_endura_uc2100×1500 135 KB](/uploads/short-url/zew2kJGL9R8PUsSulQ8JS4TaPk7.png?dl=1)

In the ColorCheckers, outer squares show the sRGB input (scene referred) while the inner squares are simulated prints. Print exposure approximately balanced for Neutral 5 patch.

</details>

### [](#p-356352-consumer-print-papers-7)Consumer print papers

[[![leaves_portra_400_crystal_archive_typeii_11cpl_-2y1m_0.9pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/4/a48dd25901b177272520012d98d5c70e81209dd3_2_222x333.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/4/a48dd25901b177272520012d98d5c70e81209dd3_2_222x333.png)

leaves_portra_400_crystal_archive_typeii_11cpl_-2y1m_0.9pe1334×2000 4.42 MB](/uploads/short-url/ntI9IhCnzijX6HRJOAGioJRa5P5.png?dl=1)

[[![leaves_portra_400_ektacolor_edge_11cpl_-2y0m_0.9pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/6/66a30b6c3369d4ae02eedef88b27562cf5a12625_2_222x333.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/6/66a30b6c3369d4ae02eedef88b27562cf5a12625_2_222x333.png)

leaves_portra_400_ektacolor_edge_11cpl_-2y0m_0.9pe1334×2000 4.38 MB](/uploads/short-url/eDY1seaVK7t8MG1uJS2E1z8uJJr.png?dl=1)

[[![leaves_portra_400_endura_premier_11cpl_-2y3m_0.9pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/b/eb295838aa352278ce5833a36f3b04fb245fa7e5_2_222x333.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/b/eb295838aa352278ce5833a36f3b04fb245fa7e5_2_222x333.png)

leaves_portra_400_endura_premier_11cpl_-2y3m_0.9pe1334×2000 4.5 MB](/uploads/short-url/xykMJjXB0zDlp0o3kMPbgq0V4i1.png?dl=1)

From left to right:

(i) Kodak Portra 400 and Fujifilm Crystal Archive TypeII print paper (gamma factor 1.1)

(ii) Kodak Portra 400 and Kodak Ektacolor Edge print paper

(iii) Kodak Portra 400 and Kodak Endura Premier print paper

Keep in mind that the saturation level is arbitrarily guessed and could be globally reduced in all the prints by reducing the concentration of DIR couplers in the film.

<details>
<summary>
Color checker comparisons (consumer print papers)</summary>

[[![cc2005_kodak_portra_400_auc_fujifilm_crystal_archive_typeii_uc](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/1/414a156700db5b2f77bee7e703198986af0324e2_2_690x492.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/1/414a156700db5b2f77bee7e703198986af0324e2_2_690x492.png)

cc2005_kodak_portra_400_auc_fujifilm_crystal_archive_typeii_uc2100×1500 135 KB](/uploads/short-url/9jzL3sXZcQtOsJHW37C7j99DKUy.png?dl=1)

[[![cc2005_kodak_portra_400_auc_kodak_ektacolor_edge_uc](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/e/fed761c4df7386b2b20042fc2e5f3d15cea4bcc8_2_690x492.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/e/fed761c4df7386b2b20042fc2e5f3d15cea4bcc8_2_690x492.png)

cc2005_kodak_portra_400_auc_kodak_ektacolor_edge_uc2100×1500 135 KB](/uploads/short-url/AmqJknFaTpVrl4MGYAlxY5Z3gAU.png?dl=1)

[[![cc2005_kodak_portra_400_auc_kodak_endura_premier_uc](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/c/1cae9a9dc28004b862b3e97274478d9cf4951cb1_2_690x492.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/c/1cae9a9dc28004b862b3e97274478d9cf4951cb1_2_690x492.png)

cc2005_kodak_portra_400_auc_kodak_endura_premier_uc2100×1500 137 KB](/uploads/short-url/45JsiBow5svh4xk8NaT3wZ6A91L.png?dl=1)

Outer squares shows the sRGB input (scene referred) while the inner squares are simulated prints. Print exposure approximately balanced for Neutral 5 patch.

</details>

### [](#p-356352-other-film-stocks-8)Other film stocks

[[![tag @ryanbreitkreutz - free raws from @signatureeditsco DSC01513](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/3/a3cc2d517e8fec0595f667c849d4ee42f6df3cf1_2_222x333.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/3/a3cc2d517e8fec0595f667c849d4ee42f6df3cf1_2_222x333.jpeg)

tag @ryanbreitkreutz - free raws from @signatureeditsco DSC015131330×2000 1.63 MB](/uploads/short-url/nn1h2SchrXFizcLFtqZJX9ocAJX.jpeg?dl=1)

[[![windows_portra_400_crystal_archive_typeii_1p1gamma_1p1cpl_-1y1m_105pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/5/c5fd6aead26e9c86eb9d9c98728788f4755f44d2_2_222x333.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/5/c5fd6aead26e9c86eb9d9c98728788f4755f44d2_2_222x333.png)

windows_portra_400_crystal_archive_typeii_1p1gamma_1p1cpl_-1y1m_105pe1330×2000 4.73 MB](/uploads/short-url/sfv0oUovJCesJKMKTxX0iihyG3M.png?dl=1)

[[![windows_pro_400h_crystal_archive_typeii_1p1gamma_10cpl_-1y1m_105pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/0/b014d2b7967788abb65d8da8dc73748894deea0f_2_222x333.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/0/b014d2b7967788abb65d8da8dc73748894deea0f_2_222x333.png)

windows_pro_400h_crystal_archive_typeii_1p1gamma_10cpl_-1y1m_105pe1330×2000 4.68 MB](/uploads/short-url/p7GEblRSAVdL5zUh3I84JxX4t7V.png?dl=1)

[[![windows_vision3_50d_crystal_archive_typeii_1p1gamma_1p1cpl_-1y1m_105pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/c/dc7b07b777e2dfc6bea93bfa5b0bdc8eeeab4438_2_222x333.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/c/dc7b07b777e2dfc6bea93bfa5b0bdc8eeeab4438_2_222x333.png)

windows_vision3_50d_crystal_archive_typeii_1p1gamma_1p1cpl_-1y1m_105pe1330×2000 4.62 MB](/uploads/short-url/vssDkuX3OfNd7pULXN5dqlTn7cs.png?dl=1)

[[![windows_gold_200_crystal_archive_typeii_1p1gamma_1p1cpl_-1y1m_105pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/9/894cfb60658079d2036b4e7e8ba5984645bbf10a_2_222x333.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/9/894cfb60658079d2036b4e7e8ba5984645bbf10a_2_222x333.png)

windows_gold_200_crystal_archive_typeii_1p1gamma_1p1cpl_-1y1m_105pe1330×2000 4.7 MB](/uploads/short-url/jACltVPm2qYlzd6S0JC3Ljb85nk.png?dl=1)

[[![windows_c200_crystal_archive_typeii_1p1gamma_1p1cpl_-1y1m_105pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/6/568751978ac4f4faa5b5f346e4eef085f0bcdc0e_2_222x333.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/6/568751978ac4f4faa5b5f346e4eef085f0bcdc0e_2_222x333.png)

windows_c200_crystal_archive_typeii_1p1gamma_1p1cpl_-1y1m_105pe1330×2000 4.74 MB](/uploads/short-url/clsYQNeYCf4ucfmAUaH9GiuWqjY.png?dl=1)

From left to right, top to bottom:

(i) image exported with darktable using sigmoid with contrast set to 2, [xmp](/uploads/short-url/yNa5ydEkOZssonVMEcL5AoyNN4e.xmp) (8.2 KB)

(ii) Kodak Portra 400

(iii) Fujifilm Pro 400h

(iv) Kodak Vision3 50d

(v) Kodak Gold 200

(vi) Fujifilm C200

All printed on Fujifilm Crystal Archive TypeII, with -1Y 1M enlarger filters, 1.1 print gamma factor, 1.05 print exposure.

<details>
<summary>
Color checker comparisons (many negatives on Fujifilm Crystal Archive TypeII)</summary>

[[![cc2005_kodak_portra_400_auc_fujifilm_crystal_archive_typeii_uc](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/1/414a156700db5b2f77bee7e703198986af0324e2_2_690x492.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/1/414a156700db5b2f77bee7e703198986af0324e2_2_690x492.png)

cc2005_kodak_portra_400_auc_fujifilm_crystal_archive_typeii_uc2100×1500 135 KB](/uploads/short-url/9jzL3sXZcQtOsJHW37C7j99DKUy.png?dl=1)

[[![cc2005_fujifilm_pro_400h_auc_fujifilm_crystal_archive_typeii_uc](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/2/42d916d616acfa367580554719554ca7d2575e40_2_690x492.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/2/42d916d616acfa367580554719554ca7d2575e40_2_690x492.png)

cc2005_fujifilm_pro_400h_auc_fujifilm_crystal_archive_typeii_uc2100×1500 133 KB](/uploads/short-url/9xmCIFHPWPw8z2Nx5TjAPidaDQc.png?dl=1)

[[![cc2005_kodak_vision3_50d_uc_fujifilm_crystal_archive_typeii_uc](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/e/7e699fd0a0393adafacb6c0f8ee761df5f87c930_2_690x492.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/e/7e699fd0a0393adafacb6c0f8ee761df5f87c930_2_690x492.png)

cc2005_kodak_vision3_50d_uc_fujifilm_crystal_archive_typeii_uc2100×1500 136 KB](/uploads/short-url/i2isxbF7cuw2HsDO6FUQ3BMAyzK.png?dl=1)

[[![cc2005_kodak_gold_200_auc_fujifilm_crystal_archive_typeii_uc](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/1/c1536254cfda57b8b4ca0ff6b583128132e2db99_2_690x492.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/1/c1536254cfda57b8b4ca0ff6b583128132e2db99_2_690x492.png)

cc2005_kodak_gold_200_auc_fujifilm_crystal_archive_typeii_uc2100×1500 135 KB](/uploads/short-url/rAeNGF6P5ZXthldnYoZezfKvann.png?dl=1)

[[![cc2005_fujifilm_c200_auc_fujifilm_crystal_archive_typeii_uc](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/b/abf1f9341905edc464fb273a6bc4aa3232e29030_2_690x492.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/b/abf1f9341905edc464fb273a6bc4aa3232e29030_2_690x492.png)

cc2005_fujifilm_c200_auc_fujifilm_crystal_archive_typeii_uc2100×1500 133 KB](/uploads/short-url/ox64xhEMNjt6chjYitTKqOeRphS.png?dl=1)

Outer squares shows the sRGB input (scene referred) while the inner squares are simulated prints. Print exposure approximately balanced for Neutral 5 patch.

</details>

Kodak Portra 400 and Gold 200 have similar identity, but Portra has more pastel colors. Vision3 50d is more neutral and flat. Pro 400h and C200 are also similar, more saturated compared to Kodak.

More results are in my recent Play Raw history ([Profile - arctic - discuss.pixls.us](https://discuss.pixls.us/u/arctic/activity)), not all of them of decent quality. Most of the progress happened in the holyday break so earlier stuff might look quite funky. Below are a couple of additional comparisons with darktable base edits (and again sigmoid with contrast set to 2).

[[![Copy of MonumentValley-tag@christianbmeza - from signatureedits.com](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/6/b6cd44b07a45db2f8ec7ef5ae7d9c6b6ff00e513_2_690x461.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/6/b6cd44b07a45db2f8ec7ef5ae7d9c6b6ff00e513_2_690x461.jpeg)

Copy of MonumentValley-tag@christianbmeza - from signatureedits.com2000×1338 1.42 MB](/uploads/short-url/q58Gt0cqwVuewQW9u4bOj22FAxJ.jpeg?dl=1)

[[![desert_fujifilm_c200_supra_endura_1stops_09pe_-4Y2M](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/5/551749c91a82b9ec67ec3768221f6aa7665ee627_2_690x461.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/5/551749c91a82b9ec67ec3768221f6aa7665ee627_2_690x461.png)

desert_fujifilm_c200_supra_endura_1stops_09pe_-4Y2M2000×1338 4.19 MB](/uploads/short-url/c8KtKgXp00PMa13wJGAsqTw42zB.png?dl=1)

The top one is the output of darktable with sigmoid, the bottom one is the simulation with Fujifilm C200 and Kodak Supra Endura paper, +1 stop exposure compensation, 0.9 print exposure, -4Y 2M filters.

[[![Copy of DSC_2070 - from signatureedits.com](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/0/f04cc9dc25ac3e9fc30eba75c6c62187b8eddb3f_2_690x460.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/0/f04cc9dc25ac3e9fc30eba75c6c62187b8eddb3f_2_690x460.jpeg)

Copy of DSC_2070 - from signatureedits.com2000×1335 1010 KB](/uploads/short-url/yhN6ULTGF5Xe8tWBcrwYfDKlMGX.jpeg?dl=1)

[[![portrait_leaves_kodak_portra_fuji_crystal_archiveii_1ev_065pe_-3Y-4M_11cpl](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/f/4f05d8c65f507ee8b879c32dd07854913ab5464a_2_690x460.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/f/4f05d8c65f507ee8b879c32dd07854913ab5464a_2_690x460.png)

portrait_leaves_kodak_portra_fuji_crystal_archiveii_1ev_065pe_-3Y-4M_11cpl2000×1335 4.24 MB](/uploads/short-url/bh4fiNQtWnBUJN6OZCTLBMOcI0q.png?dl=1)

Top darktable output, bottom simulation with Kodak Portra 400 and Fujifilm Crystal Archive TypeII, +1 stop exposure compensation, 0.65 print exposure, -3Y -4M filters.

# [](#p-356352-grain-9)Grain

The simulation builds three sub layers for each channel, imitating modern color negative films where each color layer is composed by 2-3 sublayers with different sensitivity to increase latitude. The stochastic proprieties of each layer and sublayers are imitated keeping into account that faster layers are more noisy, i.e. they have larger particles.

[[![grain_particle_area_ramp_portra_400_portra_endura](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/3/43692319e93252fb32a5ed7724dee5a47e0649b8_2_690x517.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/3/43692319e93252fb32a5ed7724dee5a47e0649b8_2_690x517.png)

grain_particle_area_ramp_portra_400_portra_endura1920×1440 2.48 MB](/uploads/short-url/9ClfeEGhSqOHzUk8lEqWmmAb2RO.png?dl=1)

These above are a few strips of Kodak Portra 400 printed on Kodak Portra Endura with vertical size of 1 mm. The average particle areas of the virtual silver halide particles, then converted in dye clouds, is changed. In first approximation, the area of the particles should be roughly proportional to the ISO. In consumer films particles are in the range 0.2 - 2 micrometer diameter, i.e. 0.03-3.2 micrometer squared.

[[![grain_chart_datasheet_kodak_vision3_50d](https://d2x313g9lpht1q.cloudfront.net/original/3X/1/8/1871ee67d3fbc37d4ba3d4027588b45d8642cd05.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/1/8/1871ee67d3fbc37d4ba3d4027588b45d8642cd05.png)

grain_chart_datasheet_kodak_vision3_50d646×584 30.7 KB](/uploads/short-url/3ufysW4gDcBPNGPg1GLgtBPJCgB.png?dl=1)

[[![grain_chart_kodak_vision3_50d](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/e/aeafb5188d4bcf6fefd91e7ced45b1c9e0ccdd3a_2_350x270.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/e/aeafb5188d4bcf6fefd91e7ced45b1c9e0ccdd3a_2_350x270.png)

grain_chart_kodak_vision3_50d1920×1440 265 KB](/uploads/short-url/oVlwW58UdDePVuZ2AEOmvw8dVeq.png?dl=1)

On the left is the only data of its kind I could find from Kodak Vision3 50d (available also for the other Vision3s). On the right is the same data virtually measured from the simulation of the same film stock with grain parameters tuned accordingly. It is computed by processing a virtual photo of a neutral gradient, then the standard deviation at each exposure is evaluated and plotted. From the peaks you can roughly see the structure in sub layers of every channel.

Here is an example with higher magnification crops with Kodak Portra 400 and Kodak Portra Endura.

[[![lowres_portra](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/0/e0f6c228831c0fee83666fa0df648f1280f526a1_2_666x1000.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/0/e0f6c228831c0fee83666fa0df648f1280f526a1_2_666x1000.png)

lowres_portra1332×1999 3.73 MB](/uploads/short-url/w67D76nGiuXIxd5pb4T2eqTJNLP.png?dl=1)

[[![print_016](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/8/9808ce9f0b9674417f6962480e6b0e0ba31d6a15_2_340x340.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/8/9808ce9f0b9674417f6962480e6b0e0ba31d6a15_2_340x340.png)

print_016901×901 1.39 MB](/uploads/short-url/lGXrzhOgvdvUEGAuGN0OByw68h7.png?dl=1)

[[![neg_016](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/b/5b241b0ff27620f1a7f970dcfc0d1ec3e71ea118_2_340x340.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/b/5b241b0ff27620f1a7f970dcfc0d1ec3e71ea118_2_340x340.png)

neg_016901×901 950 KB](/uploads/short-url/d0gNY2Bl8rCEVEM3DoxxiFAmeec.png?dl=1)

[[![print_004](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/7/675e65395d0cc0b279a4051a2d0b910a946fb105_2_340x340.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/7/675e65395d0cc0b279a4051a2d0b910a946fb105_2_340x340.png)

print_004900×900 1.32 MB](/uploads/short-url/eKrq56jmOwra0tiYkjmGWkUAeCV.png?dl=1)

[[![neg_004](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/5/45bb8ebe2da5a295aee9213e36876cf99f58d52d_2_340x340.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/5/45bb8ebe2da5a295aee9213e36876cf99f58d52d_2_340x340.png)

neg_004900×900 1.14 MB](/uploads/short-url/9WSMIoynEfx4hKleDyBm0iQqqrb.png?dl=1)

[[![print_001](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/a/ba98cd284037eeba637049ae30339370d8eafe3a_2_340x340.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/a/ba98cd284037eeba637049ae30339370d8eafe3a_2_340x340.png)

print_001896×896 985 KB](/uploads/short-url/qCIbt4IKnJz7w3gJfRagnrp2EMq.png?dl=1)

[[![neg_001](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/c/fc6661c7214e7eede7391af9148c2881888b2a1b_2_340x340.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/c/fc6661c7214e7eede7391af9148c2881888b2a1b_2_340x340.png)

neg_001896×896 958 KB](/uploads/short-url/A0PFQ9AdMRstQ1bNKcca21HC9gT.png?dl=1)

On the left the print and on the right the virtual scan of the negative. At high magnification, isolated dye clouds become visible. The highest magnification crop has a size 0.35x0.35 mm, and would correspond to an image of 5.4 giga pixels. I guess we could print a very large poster with it.

# [](#p-356352-saturation-with-dir-couplers-10)Saturation with DIR couplers

The level of saturation of the negatives is controlled via developer inhibitor release couplers (DIR couplers). When substantial density is formed in one layer, DIR couplers are released and can inhibit the formation of density in nearby regions, both in the same layer and nearby layers. The diffusion in nearby layers of DIR couplers produces increased saturation (loss of density on the other channels, i.e. purer colors), also referred as interlayer effects.

Here are a couple of examples form [signatureedits.com](http://signatureedits.com) raw files, using Fujifilm C200 and Fujifilm Crystal Archive TypeII.

[[![dir_couplers_ramp_car_fuji_c200_crystal_archive](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/e/6ecd03d18eb73cbed57a2c323e27082300bc4fd6_2_690x517.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/e/6ecd03d18eb73cbed57a2c323e27082300bc4fd6_2_690x517.png)

dir_couplers_ramp_car_fuji_c200_crystal_archive1920×1440 1.7 MB](/uploads/short-url/fObLnvWtHVT7M5FfA6Fr3xULBS6.png?dl=1)

Exposure compensation +1 stop, 0.65 print exposure, 0Y 15M filter shifts. Fujifilm negatives tends to give very saturated reds, especially at higher DIR couplers amounts. Values that I found reasonable are in the range 0.8-1.2.

[[![dir_couplers_ramp_temple_fuji_c200_crystal_archive](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/9/992f67c8e71244303e3b4032c33b2f30403dac61_2_690x517.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/9/992f67c8e71244303e3b4032c33b2f30403dac61_2_690x517.png)

dir_couplers_ramp_temple_fuji_c200_crystal_archive1920×1440 2.52 MB](/uploads/short-url/lR8ClTCCIioADhJPtRzz10va7wB.png?dl=1)

Exposure compensation +2 stops, 0.6 print exposure, 0Y 0M filter shifts.

[[![desert_kodak_gold_endura_premier_0cpl_09pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/5/9558d567aeba8367c158ba4e42cd4fe42bc47964_2_690x460.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/5/9558d567aeba8367c158ba4e42cd4fe42bc47964_2_690x460.png)

desert_kodak_gold_endura_premier_0cpl_09pe2000×1334 4.98 MB](/uploads/short-url/ljbt1TFGv1ztDwj1N3YmJKQ5heA.png?dl=1)

[[![desert_kodak_gold_endura_premier_1cpl_09pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/d/2d22f867d1a4983962ac7614839cea4f54d295bd_2_690x460.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/d/2d22f867d1a4983962ac7614839cea4f54d295bd_2_690x460.png)

desert_kodak_gold_endura_premier_1cpl_09pe2000×1334 5.01 MB](/uploads/short-url/6ripp8BV0No6aBr2GUcpHXdJZPD.png?dl=1)

In this desert photo example, the image above has no DIR couplers, while the image below has 1.0 DIR couplers amount. Using Kodak Gold 200, Kodak Endura Premier and 0.9 print exposure.

# [](#p-356352-halation-11)Halation

Having access to the physically based model, we can insert halation as a blur at the right stage of the pipeline. Usually the red channel is the mainly affected one, because it sits at the back of the film stack. Some light goes through the emulsion layers and trough the support material, then gets reflected back, gets blurred, and exposes again the emulsion. Adding for example 3% of red, 0.3% of green, and 0.1 % of blue blurred halation light, with a sigma of 200 micrometers gives the following result.

[[![halation_dots](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/b/9b88a7383a7f51a0efcbfb6b278bcc66846cfc61_2_690x115.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/b/9b88a7383a7f51a0efcbfb6b278bcc66846cfc61_2_690x115.png)

halation_dots3000×500 1.52 MB](/uploads/short-url/mbUMJAGrMvwTh81yfegHLASLYs1.png?dl=1)

In this test image every dot has an increased exposure of 1 stop of light. 14 stops in total when reaching the last dot on the right. The size of the long edge of this picture is 35 mm.

[[![armchair_vision3_crystal_archive_0halation_-4Y5M_3ev_04pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/5/a5317b8084975f5fb79ebcadc4bd0b09cb9d707a_2_690x460.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/5/a5317b8084975f5fb79ebcadc4bd0b09cb9d707a_2_690x460.jpeg)

armchair_vision3_crystal_archive_0halation_-4Y5M_3ev_04pe4000×2672 608 KB](/uploads/short-url/nzmNuraycwCPW3flndOLTs98jh0.jpeg?dl=1)

[[![armchair_vision3_crystal_archive_8halation_-4Y5M_3ev_04pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/d/3d0c3178b4836063d85bc7975c53f93e785c1bfe_2_690x460.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/d/3d0c3178b4836063d85bc7975c53f93e785c1bfe_2_690x460.jpeg)

armchair_vision3_crystal_archive_8halation_-4Y5M_3ev_04pe4000×2672 598 KB](/uploads/short-url/8I3ftvgl9ZJA7uNbHmPB0AXt2xM.jpeg?dl=1)

In this example, on the top no halation while on the bottom 8% halation of the red channel. Simulation with Kodak Vision3 to imitate Cinestill, printed on Fujifilm Crystal Archive Type II, enlarger filters -4Y 5M, +3 stops exposure compensation and 0.4 print exposure. Raw file from [signatureedits.com](http://signatureedits.com).

[[![tree_branches_kodak_gold_200_crystal_archive_preflash005_4Y10M_04pe_2ev_halation0](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/4/044d83f86aaf9984eaa20df0b3c86d2f258e8018_2_340x460.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/4/044d83f86aaf9984eaa20df0b3c86d2f258e8018_2_340x460.png)

tree_branches_kodak_gold_200_crystal_archive_preflash005_4Y10M_04pe_2ev_halation01440×1920 5.82 MB](/uploads/short-url/C3Z8xVPO9Um47b2CcvFEoGXZAA.png?dl=1)

[[![tree_branches_kodak_gold_200_crystal_archive_preflash005_4Y10M_04pe_2ev_halation3](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/d/0d967fd7160c667b203679832d914c72e4407296_2_340x460.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/d/0d967fd7160c667b203679832d914c72e4407296_2_340x460.png)

tree_branches_kodak_gold_200_crystal_archive_preflash005_4Y10M_04pe_2ev_halation31440×1920 5.75 MB](/uploads/short-url/1WcEkGbcLqBS9rEkOEONCWT5Ufc.png?dl=1)

Another example in which halation is more subtle, from a Play Raw [Nice day for a nap under a tree](https://discuss.pixls.us/t/nice-day-for-a-nap-under-a-tree/43635), thanks [@lphilpot](/u/lphilpot). Notice the warm halos through the backlit branches. Using 3% red light halation on the right image. Kodak Gold 200 and Fujifilm Crystal Archive TypeII, +2 stops, 0.4 print exposure.

# [](#p-356352-wanna-try-it-12)Wanna try it?

You can find more technical info in the GitHub repository [agx-emulsion](https://github.com/andreavolpato/agx-emulsion). If you feel adventurous you can install it. Just keep in mind that I am more of a scientist than a developer, so don’t expect too much. I think of this project as an exploration of the film simulation model, code is still quite messy, not production code by any means. All the photos here were created with version [v0.1.0](https://github.com/andreavolpato/agx-emulsion/releases/tag/v0.1.0-alpha).

# [](#p-356352-some-issues-13)Some Issues

- The conversion from RGB to spectral at the very beginning of the pipeline uses [4] that is very simple but require the input image to be converted to sRGB. I am pretty sure there are better ways to work with this. If anyone has any input it would be super appreciated. [@hanatos](/u/hanatos) you have some papers on the topic if I am not wrong
 [![:grin:](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)
- It is written in Python and quite slow (many seconds per 2K images). The temporary GUI is not color managed and just a placeholder for interacting at this stage. Plus it has a lot of parameters and might be very confusing.
- Your opinion on the results is probably what matters the most. Given the data I used, I would guess that the simulation is something like 60-85% accurate or more, which doesn’t say much.
 [![:smiley:](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)
 Any suggestion on how to compare results to real life is welcome. Any expert in film colors that can judge by eye?
 [![:nerd_face:](https://discuss.pixls.us/images/emoji/apple/nerd_face.png?v=12)](https://discuss.pixls.us/images/emoji/apple/nerd_face.png?v=12)

> Ultimately, I aim to finalize the model and its profiles, and later with some help have it running on efficient gpu code, like in vkdt. I will use this tread as a log book to report some updates, and hopefully I will manage to keep myself motivated. Possibly I would like to make a scientific publication/presentation if this is novel enough.

## [](#p-356352-references-14)References

[1] Giorgianni, Madden, Digital Color Management, 2nd edition, 2008 Wiley

[2] Hung, The Reproduction of Color, 6th edition, 2004 Wiley

[3] Jakobson, Ray, Attridge, Axford, The Manual of Photography, 9th edition, 2000 Focal Press

[4] Mallett, Yuksel, Spectral Primary Decomposition for Rendering with sRGB Reflectance, Eurographics Symposium on Rendering - DL-only and Industry Track, 2019, doi:10.2312/SR.20191216

---

## #2 **Bastian Bechtold ** (@bastibe) · 2025-02-09 21:37

This is fascinating! Thank you so much for this writeup and sharing your code!

I won’t pretend to understand the chemistry at all. But already your hints about colored grading curves and DIR couplers provide some delicious food for thought that I’ll definitely look into.

---

## #3 **jo** (@hanatos) · 2025-02-10 07:45

whoa really cool! thanks for releasing this amazing body of work and the writeup! again, there’s a quality to the images you present here that i haven’t seen in digital processes before, shows a whole new level of respect for the subject i think. will look into it in more detail and am certainly very motivated to port your code to the gpu

[![:smiley:](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)

will have many questions i think… already wondering how you’d get away with sRGB spectral upsampling…

---

## #4 **Andrea** (@arctic) · 2025-02-10 09:51

Also masking couplers are quite an interesting part of the way modern color film works. I was always puzzled by the intense color of the base of unexposed developed film. It turns out it is not simply a byproduct of the chemistry, but it has a functional role. It is a color mask that looses density with increased exposure. This to balance the unwanted absorption by the main CMY dyes formed in the layers. Adding a sort of “negative absorption” to the dyes (when compared to the base).

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/f/4/f403021fcdfd95c28f381d31e17f34360dfc6d10.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/f/4/f403021fcdfd95c28f381d31e17f34360dfc6d10.jpeg)

image635×613 70.4 KB](/uploads/short-url/yOCWMfYgX8OJI7nCVUIwuCOav04.jpeg?dl=1)

This from a excerpt that I found googling “masking couplers” that explain it better than other sources, Hunt’s book images are a bit more convoluted. From this forum too apparently [pdf link](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/c/ccc6c05a897732c28c5c396120ce83eb7b5c5194.pdf), but not sure from witch discussion.

---

## #5 **Andrea** (@arctic) · 2025-02-10 10:02

Sure I would love to discuss this more!

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

> **@hanatos** (帖子 #3):
> already wondering how you’d get away with sRGB spectral upsampling…

Film layer sensitivities are quite spectrally broad and spectrally separated. This might be part of the reason the input is not so critical. But I am still quite unaware of the nuances

of this step.

> **@hanatos** (帖子 #3):
> there’s a quality to the images you present here that i haven’t seen in digital processes

I believe that using a fully absorptive spectral pipeline and saturation boost inspired by density inhibition, mimicking interlayer effects, might contribute to why images look very “dense” and with film colors. Going to the root of this and generalizing better might be interesting, though.

---

## #6 **jo** (@hanatos) · 2025-02-10 10:26

okay i had a quick look over the code, but i couldn’t speak python to save my grandmother

[![:smiley:](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)

so a few questions:

you have tensor diagram contractions, super cool! how many spectral bands are you using? do we have a memory problem?

if i understand correctly the spectral quantities here are *densities* of some dyes / developed grains and such. i mean, these are <span class="math">[0,\infty)</span>, as opposed to transmittances/colours that would be <span class="math">[0,1]</span>, right? but even with inhibitors never negative?

smooth spectra are great, they compress well. choosing the right representation might be important for an efficient implementation.

and yes, i think i can provide code for all possible and impossible spectral upsampling methods.

---

## #7 **Andrea** (@arctic) · 2025-02-10 13:52

> **@hanatos** (帖子 #6):
> how many spectral bands are you using? do we have a memory problem?

I am using a spectral range 380-780 nm every 5 nm. It is probably overkilling, but I looked at the spectra and eyeballed the step to not ruin the peaks to much. Steps of 10 nm looked too rough for the unmixing/fitting when creating the profiles. The output of the actual simulation might be much less sensitive. It is configured in `agx_emulsion/config.py` in the `SPECTRAL_SHAPE = colour.SpectralShape(380, 780, 5)` constant. Haven’t tested to change it for now. The profiles need to be recomputed in case.

This is an example of the actual spectra and curves used in the calculation:

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/9/e9d48b6352bfda17e814a52d7fdf73529ddb7dd0_2_690x229.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/9/e9d48b6352bfda17e814a52d7fdf73529ddb7dd0_2_690x229.png)

image1200×400 64.7 KB](/uploads/short-url/xmyCKMb7j7EnYYdrOG8VI6rQsLK.png?dl=1)

Left curves are effective absorptions of layers; center curves are the conversion of log-exposure to density, then scaled by the CMY spectra on the right for the final density spectrum of each pixel. This happening both for negative and print.

I definitely have a memory problem for larger images. For now, I didn’t optimize at all for it.

[![:grin:](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)

 I focused mainly on the “quality” of the model.

> **@hanatos** (帖子 #6):
> if i understand correctly the spectral quantities here are densities of some dyes / developed grains and such.

There are densities (proportional to the amount of dyes and also related to transmittance) and exposures (amount of light absorbed/transmitted etc., `raw` sometimes in the code). Both positive unbounded. In the interpolation of characteristic density curves and inhibitors calculations, exposures is used as log10(exposure) or called `log_raw` with range <span class="math">(-\infty, \infty)</span>.

This from `emulsion.py` is the heart of the film part:

```
log_raw = np.log10(raw + 1e-10)
density_cmy = self._interpolate_density_with_curves(log_raw)
density_cmy = self._apply_density_correction_dir_couplers(density_cmy, log_raw, pixel_size_um)
density_cmy = self._apply_grain(density_cmy, pixel_size_um, compute_reference_exposure)
density_spectral = self._compute_density_spectral(density_cmy)

```

The CMY densities (non spectral, `density_cmy` has three channels) in each pixel are stochastically “chunked” for creating the grain, using Poission/Binomial random numbers.

---

## #8 **Jakob Andrén** (@jandren) · 2025-02-10 15:29

Love it!

Wanted to learn this stuff when I worked on the sigmoid module, especially related to methods for handling wide gamuts better, but could find good sources like you. Will try to have time to read them and try out your stuff. Looking forward to follow along in your progress.

---

## #9 **Daniel, who likes dt and digikam** (@DanielLikesDT) · 2025-02-10 21:16

I am also able to run your software (I had issues in pycharm / matplotlib and I had to copy the img folder into the gui folder) - which is great! I was only able to test your grain and must say: it is a very smooth type of grain. Nice.

If you need someone to test features or do simple stuff (I know a tiny bit of python) I would love to assist. This looks very promising.

---

## #10 **Andrea** (@arctic) · 2025-02-11 00:14

Hey [@jandren](/u/jandren)! Nice to hear that you are interested in this.

I can add a couple of plots that might start a discussion, or at least trigger some thinking.

Online sometimes you can find LUT tested against “stress test images”. For sRGB inputs often this one is used ([3dlutcreator link](https://3dlutcreator.com/3d-lut-creator---materials-and-luts.html)):

[[![cc05](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/b/1bb1926201ac71ef9a682c974e15d8f0d0fa92f2_2_200x100.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/b/1bb1926201ac71ef9a682c974e15d8f0d0fa92f2_2_200x100.png)

cc051000×500 454 KB](/uploads/short-url/3WZkVwGlxx4MzSWNr280TayBq0i.png?dl=1)

I don’t like it too much because it is not very smooth from the beginning. But let’s have a look.

Taking only the left square (only a few columns of the image actually) and plotting it in a chromaticity plot gives the following.

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/d/7/d733c953565f2e8a4c3a7401fea5d7db99ccee61.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/d/7/d733c953565f2e8a4c3a7401fea5d7db99ccee61.png)

image630×628 69.3 KB](/uploads/short-url/uHLBHmUb33HQsmG4wKlUsOK7Eyt.png?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/d/f/dfd14008653d3acc4c0c3d86e6cf03c61310c051.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/d/f/dfd14008653d3acc4c0c3d86e6cf03c61310c051.jpeg)

image389×389 20.1 KB](/uploads/short-url/vVYN7nrQ9dxxVQYnOwlaq2nCkLv.jpeg?dl=1)

All the extreme values of sRGB are reached. The lower part of the stress test image runs over the edge of the gamut, while the top part desaturates and goes towards D65 white.

I was curious to see how the chromaticity plot would be mapped after the simulation. The stress test image is not scene referred, so the print will be quite dark (small latitude), but might still give some insight.

This is using high saturation Kodak Gold and Endura Premier paper.

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/f/7/f7801a63278f5e21e5ac03619a02bc1aaac7b2eb.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/f/7/f7801a63278f5e21e5ac03619a02bc1aaac7b2eb.png)

image630×628 106 KB](/uploads/short-url/zjuotvMcuqHMQzeVFGQ7jY1bULN.png?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/1/6/1646f62fdbb6ef07e07b29e2007774e1f2bbf249.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/1/6/1646f62fdbb6ef07e07b29e2007774e1f2bbf249.jpeg)

image389×389 21.3 KB](/uploads/short-url/3b4xq00mmg1Ikx4319MQnbWhUc9.jpeg?dl=1)

This is using low saturation Portra film and paper.

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/1/7/174f886aec86b7a1d7928bcce6ca76ca2aa53abb.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/1/7/174f886aec86b7a1d7928bcce6ca76ca2aa53abb.png)

image630×628 89.3 KB](/uploads/short-url/3kdnzCcAdn1Ajlg8ogt5F51Tr7B.png?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/8/e/8e33c94eeb551a0023e7e16d05ea5f4d52d5734e.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/8/e/8e33c94eeb551a0023e7e16d05ea5f4d52d5734e.jpeg)

image389×389 19.4 KB](/uploads/short-url/khYKESlBXDGg7MxLAvpYrgqhZ6e.jpeg?dl=1)

I note that shadows now desaturate towards black, and curves from white to black are mostly smooth, with some funky twists (the curves are coming from the columns of the stress test image). Also the gamut stretches outside sRGB, especially on the blue green side.

---

## #11 **Andrea** (@arctic) · 2025-02-11 00:23

Great that you managed to run the program! I am glad of the interest

[![:smiley:](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)

---

## #12 **Artaga** (@Artaga734) · 2025-02-11 12:22

I’ve been able to launch the program and play around with some of my own pictures. For now I pretty much kept the defaults and played only with film stock, paper and print exposure. I really like the feel of the results, especially for the robin. Thanks for the tool [@arctic](/u/arctic) !

Kodak gold 200 and ektacolor (left) - Kodak gold 200 and fujifilm crystal archive (right)

[[![bench_ektacolor](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/2/02318448a7c4b71e5578891ed9ba06f4b004218d_2_241x301.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/2/02318448a7c4b71e5578891ed9ba06f4b004218d_2_241x301.jpeg)

bench_ektacolor1638×2048 788 KB](/uploads/short-url/jp2JlafVCEkpwHEo8SiDuu4o1L.jpeg?dl=1)

[[![bench_fuji](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/2/227152ddd2b100e5c45b65e12b9047bd4f3491c6_2_241x301.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/2/227152ddd2b100e5c45b65e12b9047bd4f3491c6_2_241x301.jpeg)

bench_fuji1638×2048 813 KB](/uploads/short-url/4UH1N4VQv43POD8PCLV6VTwPZBk.jpeg?dl=1)

Robin with fujifilm c200 and kodak supra endura

Original lacking a bit of exposure :

[[![robin2_c200_supra_endura](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/f/0fb4d75b62c9dd9f8ce2d867e025f21b1770eaa2_2_34x25.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/f/0fb4d75b62c9dd9f8ce2d867e025f21b1770eaa2_2_34x25.jpeg)

robin2_c200_supra_endura2048×1535 273 KB](/uploads/short-url/2eWBYV8861a4fuBoKbUvNJ4jNS2.jpeg?dl=1)

With more exposure (left) - Changing color filters y shift +2 m shift +3 (right)

[[![robin2_c200_supra_endura_y_p0_m_p0_pexp_1_5](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/a/0af1b21475e82c4b3f6c7b1535d025f9b16e6340_2_276x206.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/a/0af1b21475e82c4b3f6c7b1535d025f9b16e6340_2_276x206.jpeg)

robin2_c200_supra_endura_y_p0_m_p0_pexp_1_52048×1535 335 KB](/uploads/short-url/1yOBwmfqFYeU2qDl3SRZDjbjPag.jpeg?dl=1)

[[![robin2_c200_endura_premier_y_p2_m_p3_pexp_1_5](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/9/e94110c78b186833273c07e69cb9df7616462366_2_276x206.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/9/e94110c78b186833273c07e69cb9df7616462366_2_276x206.jpeg)

robin2_c200_endura_premier_y_p2_m_p3_pexp_1_52048×1535 325 KB](/uploads/short-url/xhsEtKGPq9PJBBpD9gcwSkWdKei.jpeg?dl=1)

With crystal archive paper :

[[![robin2_c200_crystal_archive_y_p0_m_p0_pexp_1_5](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/1/819d8f8d82b3547308a96721757118c8e2aba367_2_517x387.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/1/819d8f8d82b3547308a96721757118c8e2aba367_2_517x387.jpeg)

robin2_c200_crystal_archive_y_p0_m_p0_pexp_1_52048×1535 340 KB](/uploads/short-url/iuDaih2eVTAGrUrMqMSF3oHQ0th.jpeg?dl=1)

---

## #13 **Andrea** (@arctic) · 2025-02-11 12:26

Amazing!

[![:sunglasses:](https://discuss.pixls.us/images/emoji/apple/sunglasses.png?v=12)](https://discuss.pixls.us/images/emoji/apple/sunglasses.png?v=12)

If you want to play with something I reccomend you to change this:

- print exposure: to brighten or darken the image
- negative exposure: boost it if the shadows become underexposed, it should not affect much the image otherwise
- critical is the use of color filters. Y filter makes the image warmer or colder, M filter makes the image more magenta or green. Essentially fine tune of the white balance.

This is the core of the RA4 printing control system.

---

## #14 **Daniel, who likes dt and digikam** (@DanielLikesDT) · 2025-02-11 19:47

What a monster software - in the most positive sense.

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/4/b4c38d909b2372be1e352b7fa40490e5f88cd411_2_690x290.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/4/b4c38d909b2372be1e352b7fa40490e5f88cd411_2_690x290.jpeg)

image2600×1093 1.57 MB](/uploads/short-url/pN6UJm2untnKYybywuaIMBKMFvH.jpeg?dl=1)

It completely depletes my not too shabby desktop PC with 32 GB of RAM just to compute the above visible cropped image. Many of the buttons feel like magic but they work as the tool tip says (pre-flash was a big surprise for someone who has not the slightest idea of analog film development). Great! Please keep working.

---

## #15 **Andrea** (@arctic) · 2025-02-12 08:03

Definitely there is some optimization to be done in the future to reduce the memory usage.

[![:grin:](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)

Regarding preflashing I have a very good example from a Play Raw [High contrasts in a man made wilderness](https://discuss.pixls.us/t/high-contrasts-in-a-man-made-wilderness/43415), from [@Popanz](/u/popanz).

Print paper has limited latitude and predefined contrast, while film negatives can capture a very large dynamic range (easily 10+ stops). Preflashing is a simple hack of the printing process to retain some of the highlight details. Print paper is essentially flashed with some light before the negative projection, i.e. making it more gray-ish and taming down the highlights (have a look at this video for a real life example [https://www.youtube.com/watch?v=lcx4ag7iygI](https://www.youtube.com/watch?v=lcx4ag7iygI)). The price to pay is reduced contrast and saturation.

[[![garden_pro_400h_crystal_archive_typeii_1.0cpl_0preflash_0Y0M_015pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/3/5394800ce895e24536b8901c3e20a8b7e0ab56fa_2_690x460.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/3/5394800ce895e24536b8901c3e20a8b7e0ab56fa_2_690x460.png)

garden_pro_400h_crystal_archive_typeii_1.0cpl_0preflash_0Y0M_015pe1999×1334 5.14 MB](/uploads/short-url/bVnMZJa9zPH8YCX3R0uuivXNqMG.png?dl=1)

[[![garden_pro_400h_crystal_archive_typeii_1.0cpl_001preflash_0Y0M_015pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/4/54842f9e8b81f4b38172d4381a30e2fd8881fc9d_2_690x460.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/4/54842f9e8b81f4b38172d4381a30e2fd8881fc9d_2_690x460.png)

garden_pro_400h_crystal_archive_typeii_1.0cpl_001preflash_0Y0M_015pe1999×1334 5.07 MB](/uploads/short-url/c3FjvSo4sKL0VT13uiT4FyOkJL7.png?dl=1)

Using Fujifilm Pro 400h with +4 stops of exposure compensation, Fujifilm Crystal Archive TypeII with 0.15 print exposure.

On the top no preflashing while on the bottom 0.01 preflashing exposure through an unexposed film base (by default in the sim preflashing exposure is considered trough unexposed film). You can also tint preflashing by changing enlarger filters compared to the negative print exposure.

---

## #16 **Steven** (@123sg) · 2025-02-12 13:46

This is awesome… I don’t have the knowledge to understand all that is involved, but I can recognize the massive amount of work that’s gone into this, and the results look stunning.

I’m 100% windows at present, but when I have time will look into running up a VM perhaps…

Unless I’ve missed the obvious and there’s a better way to get it running.

[![:wink:](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)

---

## #17 **Daniel, who likes dt and digikam** (@DanielLikesDT) · 2025-02-12 14:02

You can run it under windows - no problem. Just install pycharm or some other python IDE and this should work.

---

## #18 **Artaga** (@Artaga734) · 2025-02-12 16:10

I can confirm that it is running with Pycharm on Windows, just make sure that the working directory is right, when running it directly from Pycharm’s IDE.

If testing on a small screen like a laptop, I have found it useful to change this line to the following :

```
viewer.window.add_dock_widget(simulation, area="right", name='main', tabify=True)
# Change tabify to True

```

Otherwise the run button gets lost out of frame.

---

## #19 **Andrea** (@arctic) · 2025-02-12 17:08

I usually run the GUI straight form the terminal from the main package folder, e.g. if using `conda` and following the instruction in the repo README:

```
> conda activate agx-emulsion
> cd \path\to\main\repo\folder\
> python agx_emulsion\gui\main.py

```

Keep in mind that everything GUI related is very rudimentary.

---

## #20 **nosle** (@nosle) · 2025-02-12 19:02

My python skills are non existent and running debian I don’t have conda it seems. My attempts at venv fails with a segfault when executing. Anyone got any tips?

This looks like a great project!

---

## #21 **Liam Collod** (@liam_collod) · 2025-02-13 15:38

Very cool project ! I did not had time to explore it yet but it looks fascinating.

For those who struggle to install it, nowadays you can use [uv](https://docs.astral.sh/uv) to manage and install python programs.

With absolutely nothing installed on your system (not even python) you just need to execute the following:

<pre data-code-wrap="bash"><code class="lang-bash"># ! you only need to exeucte this command the first time to install uv!
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

cd path/to/agx-emulsion/download/dir

# ! you only need to execute this command the first time !
# this will take some time to run because it needs to cache all the dependencies
uv run --python 3.11 --with-requirements requirements.txt --no-project --with-editable . imageio_download_bin freeimage

# and this the command you will call everytime to launch the program
uv run --python 3.11 --with-requirements requirements.txt --no-project --with-editable . agx_emulsion/gui/main.py
</code></pre>

the above works for Windows on powershell, on other system you probably just need to edit the command to install uv by looking at their manual: [Installation | uv](https://docs.astral.sh/uv/getting-started/installation/#standalone-installer)

And [@arctic](/u/arctic) to get rid of the annoying imageio download step you could use another image IO library like [OpenImageIO](https://openimageio.readthedocs.io), they recently made themselves available as [pip package](https://pypi.org/project/OpenImageIO/).

---

## #22 **Steven** (@123sg) · 2025-02-13 19:50

So I have it running in Windows 11 now - eventually realised all I had to do was install Anaconda then pretty much follow the instructions in the readme…

Me like it! Lot of learning to do to mnake the most of it, and I appreciate it’s still at the experimental stage but loving the results on some photos. Just shared one [here.][[Capture Challenge] Charge your battery and take some photos - #2913 by 123sg](https://discuss.pixls.us/t/capture-challenge-charge-your-battery-and-take-some-photos/31798/2913)

---

## #23 **nosle** (@nosle) · 2025-02-13 20:00

Thanks for the uv tip. On debian I made a venv environment, pip installed uv and then copy pasted your uv commands. It worked!

---

## #24 **Felix Kloss** (@luator) · 2025-02-13 21:04

This looks really awesome! I just gave it a quick try, mostly with default settings (the amount of options overwhelms me a bit :D) and the result looks really great. I’ll definitely play around with it a bit more when I have some time.

---

## #25 **Sakari** (@flannelhead) · 2025-02-13 21:13

So awesome to see how far you have got by starting from first principles and the underlying chemical processes. Looks awesome so far, looking forward to peek into the code and try it some more!

What would it take to use images that exceed the sRGB limits? [This repo](https://github.com/sobotka/Testing_Imagery) is a treasure trove of test images, and most are linear BT.709 encoded OpenEXR that have negative values for some of the components. As far as I can tell, the program expects values that have been encoded with the sRGB inverse EOTF.

---

## #26 **nosle** (@nosle) · 2025-02-13 21:41

Been testing it and I feel like I’m looking at my scans! Takes a while to understand the knobs because I never developed colour myself.

I’m curious as to why my photos need huge up towards -40 ev exposure compensation to show anything?

I’m exporting from Rawtherapee and the imported files look very contrasty on import when they are extremely flat in other viewers.

---

## #27 **Steven** (@123sg) · 2025-02-13 22:11

> **@nosle** (帖子 #26):
> imported files look very contrasty on import when they are extremely flat in other viewers.

I’ve noticed that too, importing 16bit tiffs from darktable, but once I run the simulation they seem fine - the excess contrast disappears.

> **@nosle** (帖子 #26):
> I’m curious as to why my photos need huge up towards -40 ev exposure compensation to show anything?

Mine don’t need that… interesting - maybe a colour profile issue? I am using the auto exposure though.

---

## #28 **Andrea** (@arctic) · 2025-02-13 22:12

> **@liam_collod** (帖子 #21):
> For those who struggle to install it, nowadays you can use uv to manage and install python programs.
With absolutely nothing installed on your system (not even python) you just need to execute the following:

Thanks a lot for the instructions, I didn’t know about `uv`! I will definetily have a look at it.

> **@liam_collod** (帖子 #21):
> And @arctic to get rid of the annoying imageio download step you could use another image IO library like OpenImageIO, they recently made themselves available as pip package.

Oh nice! Also great suggestion.

> **@flannelhead** (帖子 #25):
> What would it take to use images that exceed the sRGB limits?

For now what limits the input color space is the way I am converting RGB to spectral data at the very beginning of the pipeline. I am using this [colour.recovery.RGB_to_sd_Mallett2019](https://colour.readthedocs.io/en/develop/generated/colour.recovery.RGB_to_sd_Mallett2019.html#colour.recovery.RGB_to_sd_Mallett2019) that is very convenient, robust and fast but works only for sRGB. A different spectral input conversion could allow wider gamuts. I have the feeling that it would not change a lot the results, given the wide absorptions of the film layers. But of course we should experiment and verify.

> **@nosle** (帖子 #26):
> I’m curious as to why my photos need huge up towards -40 ev exposure compensation to show anything?

That sounds very strange, I’ve never used more than a few ev of compensation with the camera auto-exposure active. Could you share a .pp3 or a low res file you use so I can reproduce it? Do you export PNG 16bit and import using the `filepicker` widget? Importing directly with napari for example might not work well and convert to 8 bit.

---

## #29 **Andrea** (@arctic) · 2025-02-13 22:13

> **@123sg** (帖子 #22):
> Me like it! Lot of learning to do to mnake the most of it, and I appreciate it’s still at the experimental stage but loving the results on some photos. Just shared one [here.][Capture Challenge] Charge your battery and take some photos - #2913 by 123sg

That looks impressive!

[![:slightly_smiling_face:](https://discuss.pixls.us/images/emoji/apple/slightly_smiling_face.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slightly_smiling_face.png?v=12)

---

## #30 **Andrea** (@arctic) · 2025-02-13 22:31

I did a couple of mini optimization on the main branch.

Mainly, I reduced the wavelength step of spectral calculations from 5 nm to 10 nm, sacrificing a little accuracy for sake of efficiency. I didn’t notice big changes, but the spectra (especially for filters and film/print absorptions) are tightly sampled and look a bit ugly.

With these minimal changes I managed to process on my laptop (32GB of ram) a 20 megapixel image. Kodak Gold 200 and Portra Endura, raw file from [signatureedits.com](http://signatureedits.com).

[[![gold200_portra_default](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/b/3b9087f6f23486265d8231924174eb5a286ec712_2_666x999.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/b/3b9087f6f23486265d8231924174eb5a286ec712_2_666x999.jpeg)

gold200_portra_default3753×5634 2.23 MB](/uploads/short-url/8uVPhTnQ4nETehAk16eq3KSIzv4.jpeg?dl=1)

I also have in mind a couple of major optimizations that could facilitate the translation in gpu (I think), and drastically reduce memory needs, keeping a 5 nm step. I will soon prototype with it and update here.

---

## #31 **Bob** (@PhotoPhysicsGuy) · 2025-02-14 00:28

WOW!

[@arctic](/u/arctic) , I don’t know of any effort to simulate film in this depth.

You basically mimic every physical step of film development. And as far as I can see it really pays off.

Preflashing and DIR simulation, a proper grain size distribution simulation?

I’m floored.

This is beyond comprehension how complete this simulation is.

Kudos.

I’ll look where I have the Kodak stuff, where they describe Cine-filmstock (before the Vision filmstocks) from the 70ies or 80ies…somewhere on my harddrive.

my mind is properly blown.

EDIT: found it! From before ECN-2 developer chemistry. It even contains dye-ageing estimation plots…

[![:smirk:](https://discuss.pixls.us/images/emoji/apple/smirk.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smirk.png?v=12)

---

## #32 **Y** (@Y69) · 2025-02-14 06:31

What a thorough approach!

Sadly, it segfaults in `libpython3` on my machine - I need to debug it properly

[![:frowning:](https://discuss.pixls.us/images/emoji/apple/frowning.png?v=12)](https://discuss.pixls.us/images/emoji/apple/frowning.png?v=12)

---

## #33 **Daniel, who likes dt and digikam** (@DanielLikesDT) · 2025-02-14 06:47

You might try and upgrade all the imports from the requirements. It helped me to get things running. Using pycharm.

---

## #34 **Andrea** (@arctic) · 2025-02-14 08:41

Thank you for the kind words [@PhotoPhysicsGuy](/u/photophysicsguy).

> **@PhotoPhysicsGuy** (帖子 #31):
> EDIT: found it! From before ECN-2 developer chemistry. It even contains dye-ageing estimation plots…

Interesting! I’m becoming kind of a collector of technical documents from Kodak. It would be nice to have a look at them. My sources for technical documents have been these websites: [Index of /docs/film](https://125px.com/docs/film/), [Photographic & Darkroom Products by Brand](https://www.digitaltruth.com/products/), [Browse The Analog Film Stock Library | Filmtypes](https://www.filmtypes.com/films), [https://analogfilm.space/](https://analogfilm.space/).

I also noticed that older datasheets from Kodak tend to have better quality. Newer ones can have images copy-pasted from older ones, so I usually opted for the oldest when I could choose.

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

> **@PhotoPhysicsGuy** (帖子 #31):
> a proper grain size distribution simulation?

Regarding grain, I am fitting characteristics curves D-LogE with three normal CDFs (for three sublayers). This is an ok minimal model if we assume a lognormally distributed area of silver halide particles in every layer (that roughly is, from old references), and sensitivity proportional to the area of particles. So the multi layer structure directly arises from the curves themselves. Here is an example plot of a fitted structure.

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/7/2/7240a569d3f6171375730a6fd3f461de2f37b19d.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/7/2/7240a569d3f6171375730a6fd3f461de2f37b19d.png)

image567×432 44.6 KB](/uploads/short-url/giIVZwyKVsxOJKiLYDaF3NOvvbL.png?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/8/4/847b945676dd57683df85038ee754cfac91886b6.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/8/4/847b945676dd57683df85038ee754cfac91886b6.png)

image576×432 45.8 KB](/uploads/short-url/iTZNdvKhisjVtHFhGCcs1I4DivA.png?dl=1)

Then adjusting binomial (for probability of development) and Poisson (for random position of particles) distributions for each layer we can mock a decent RMS granularity profile.

An aspect, that I was super surprised of, is that film has embedded “chemical sharpening”. DIR couplers released in high density areas, diffuses in space (about 10-15 um) and produces local contrast with surrounding lower density parts of the image, inhibiting them. That sounds kind of crazy to me.

---

## #35 **Bob** (@PhotoPhysicsGuy) · 2025-02-14 10:10

> **@arctic** (帖子 #34):
> My sources for technical documents have been these websites:

Oh, this is great!

> **@arctic** (帖子 #34):
> Then adjusting binomial (for probability of development) and Poisson (for random position of particles) distributions for each layer we can mock a decent RMS granularity profile.

Decent is a bit of an understatement here. I would qualify this as a very complex grain model. Could also be that I am unaware of other grain modeling efforts though.

> **@arctic** (帖子 #34):
> DIR couplers released in high density areas, diffuses in space (about 10-15 um) and produces local contrast with surrounding lower density parts of the image, inhibiting them. That sounds kind of crazy to me.

Ahhh! That’s why some MTF plots for film have above 1 transfer at higher frequencies. I always thought only stand-developer kind of local developer depletion could do this (like simulated in Filmulator), which of course isn’t possible in cine-film development.

> **@arctic** (帖子 #34):
> It would be nice to have a look at them.

Sure! I’ll PM you.

---

## #36 **Bastian Bechtold ** (@bastibe) · 2025-02-14 11:01

> **@arctic** (帖子 #34):
> An aspect, that I was super surprised of, is that film has embedded “chemical sharpening”. DIR couplers released in high density areas, diffuses in space (about 10-15 um) and produces local contrast with surrounding lower density parts of the image, inhibiting them. That sounds kind of crazy to me.

I think that’s what filmulator implemented!

(As an aside, the chemical sharpening clearly operates on small areas; I believe that a part of “the medium format look” was the different size of this sharpening, relative to the negative size. It seems that some image editing programs still rely on pixel sizes in their sharpening algorithms, which exhibits a similar difference for high-megapixel images.)

---

## #37 **Bob** (@PhotoPhysicsGuy) · 2025-02-14 11:24

> **@bastibe** (帖子 #36):
> (As an aside, the chemical sharpening clearly operates on small areas; I believe that a part of “the medium format look” was the different size of this sharpening, relative to the negative size. It seems that some image editing programs still rely on pixel sizes in their sharpening algorithms, which exhibits a similar difference for high-megapixel images.)

I 100% agree with this.

---

## #38 **Andrea** (@arctic) · 2025-02-14 17:42

> **@PhotoPhysicsGuy** (帖子 #35):
> always thought only stand-developer kind of local developer depletion could do this

As far I understood, DIR couplers sharpening will happen in normally agitated development, and will affect only very short range, depending on the diffusion properties of the couplers molecules in the emulsion phase. A reasonable guess is 10-15 um, but I need a better reference for this.

[![:grin:](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)

> **@bastibe** (帖子 #36):
> I think that’s what filmulator implemented!

I didn’t know about that, I should definitely dig more into the filmulator project.

> **@bastibe** (帖子 #36):
> (As an aside, the chemical sharpening clearly operates on small areas; I believe that a part of “the medium format look” was the different size of this sharpening, relative to the negative size. It seems that some image editing programs still rely on pixel sizes in their sharpening algorithms, which exhibits a similar difference for high-megapixel images.)

I also agree here. In the simulation the diffusion parameter of the DIR couplers is in micrometers. So changing the size of the film negative (`film_format_mm`) will take into account this.

---

## #39 **Y** (@Y69) · 2025-02-14 19:00

Cool, switching to compatible releases did the trick for me. Sent it as a PR.

---

## #40 **Ted Cousins** (@cedric) · 2025-02-14 22:35

> **@arctic** (帖子 #38):
> Chat-GPT suggests 10-15 um

Caution [@arctic](/u/arctic) , I was told firmly by admin a few days ago to <span class="bbcode-u">stop</span> quoting AI responses …

---

## #41 **nosle** (@nosle) · 2025-02-14 22:48

> **@arctic** (帖子 #28):
> That sounds very strange, I’ve never used more than a few ev of compensation with the camera auto-exposure active. Could you share a .pp3 or a low res file you use so I can reproduce it? Do you export PNG 16bit and import using the filepicker widget? Importing directly with napari for example might not work well and convert to 8 bit.

I’ve now tested in on two computers and files from various cameras. All similar requiring between -30 and -40 ev compensation.

Boring sample photo:

[[![beach02](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/e/7ecc682760e97abe8d4a939311b546d33b48c4a9_2_690x457.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/e/7ecc682760e97abe8d4a939311b546d33b48c4a9_2_690x457.jpeg)

beach022048×1358 476 KB](/uploads/short-url/i5I6fZAH1MOppBIUaljdAyjqCPn.jpeg?dl=1)

[[![beach02](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/e/4e088f17bbbc5ebd91aaa69fcaad36eef6436c01_2_690x457.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/e/4e088f17bbbc5ebd91aaa69fcaad36eef6436c01_2_690x457.png)

beach021024×679 3.4 MB](/uploads/short-url/b8jzYbzSRX6rhvNJdOwR90VbDqx.png?dl=1)

[beach02.pp3](/uploads/short-url/kJmozPAqxoh1lRZC9X7cbVgeMlS.pp3) (15.0 KB)

[[![2025-02-14-234126_1397x663_scrot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/8/48e5230109749e2dd13ee9a82c80bbd83fe7649a_2_690x327.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/8/48e5230109749e2dd13ee9a82c80bbd83fe7649a_2_690x327.png)

2025-02-14-234126_1397x663_scrot1397×663 989 KB](/uploads/short-url/aoRiFhvR1qTZmZdogNEqTlEF29c.png?dl=1)

---

## #42 **Cameron Rad** (@cameronrad) · 2025-02-15 05:46

Wow, this is really cool! Great work! I look forward to playing around with it more and seeing it develop.

[![:slightly_smiling_face:](https://discuss.pixls.us/images/emoji/apple/slightly_smiling_face.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slightly_smiling_face.png?v=12)

Also thanks [@liam_collod](/u/liam_collod) for those installation instructions. It made it extremely easy on my macOS system.

---

## #43 **Daniel, who likes dt and digikam** (@DanielLikesDT) · 2025-02-15 11:29

[@arctic](/u/arctic) : Is there any way to see a version of the image without heavy simulation (without de selecting the layer altogether)?

I would really like to be able to see what settings have what impact on be the image.

At the moment it feels like try and error (which is probability how it really was back in the days).

Another issue is the massive loss of details I get pretty much independently of the settings. What am I missing? Or is it really meant to work this way?

---

## #44 **Andrea** (@arctic) · 2025-02-15 12:15

> **@DanielLikesDT** (帖子 #43):
> Is there any way to see a version of the image without heavy simulation (without de selecting the layer altogether)?

For now switching layers is the only way I think. By renaming a layer you can save snapshots done with different settings and compare them

I agree that everything is very rough in the interface. I don’t plan to stick with `napari`+`magicgui`, it is just a quick GUI to be able to test things fast (and let people try at this stage). I think this sim should be more like a module to be integrated somewhere else where this features are already in place.

> **@DanielLikesDT** (帖子 #43):
> I would really like to be able to see what settings have what impact on be the image.

There are a lot of controls for sure. If overwhelmed start with this ones:

> **@arctic** (帖子 #13):
> print exposure: to brighten or darken the image
negative exposure: boost it if the shadows become underexposed, it should not affect much the image otherwise
critical is the use of color filters. Y filter makes the image warmer or colder, M filter makes the image more magenta or green. Essentially fine tune of the white balance.

plus:

- grain >> particle area um2, for increasing or reducing grain
- couplers >> dir couplers amount, for increasing reducing saturation

I could extend the README with a better quick-start guide if this will help.

> **@DanielLikesDT** (帖子 #43):
> Another issue is the massive loss of details I get pretty much independently of the settings. What am I missing? Or is it really meant to work this way?

There is a small gaussian blur applied by default at the density level right after generating grain (grain >> blur = 0.6 in pixels). You can set it to 0.55 or 0.5, or even zero. There is also sharpening done in the “scanner”, I would set `scan unsharp mask` to (0.7, 0) if you switch off grain blur completely. I usually test this things on a small crop of the image using “input >> crop” and “compute full image” (full resolution cropped image). Then when happy with the texture I get back to uncropped editing with a downscaled preview.

I would say that this is partially intended to get a smoother-correlated grain texture, and it will work better in higher resolution images. Especially when after optimizing the sim, it will not take ages to do full-res processing.

---

## #45 **Andrea** (@arctic) · 2025-02-15 12:19

Not sure why this is happening but i committed a small fix that should take care of this. Thanks for the files.

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

---

## #46 **** (@ChrisB) · 2025-02-16 18:59

Hello,

your project looks promising and I have been reading with great interest this conversation.

I have been able to run the app (thanks Liam!) but so far I cannot get a “good” result.

I have tried to do the following:

- load a “linear_rec709” exr file (“linear” transfer function and “bt.709” primaries) into Nuke
- convert it to png 16bit. This is the part I get confused: should I keep the transfer function “linear” or not ?

Then I load the png into the software and I get strange results. It looks very dark or completely washed-out.

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/1/31f8b5644c8539fb8771ee7a7114c30131d47ccd_2_690x388.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/1/31f8b5644c8539fb8771ee7a7114c30131d47ccd_2_690x388.jpeg)

image980×552 115 KB](/uploads/short-url/784fBuhheGQ5nxmtNxnukE9InpP.jpeg?dl=1)

Maybe I got confused about these parameters:

- “apply cctf decoding”
- “output cctf decoding”
- “compute full image”

Thanks for the help !

---

## #47 **nosle** (@nosle) · 2025-02-16 19:47

From my testing I would recommend starting without tweaking any settings. Then turning off auto exposure and then dialling in manual exposure.

The full image tickbox creates a full resolution layer with the applied settings. When not ticked a low Res version is created to judge overall effect. Size, crop etc of this preview is determined in the input tab.

The software is extremely slow so I wouldn’t recommend checking tha full image box until you’re happy with the overall tones.

---

## #48 **Ted Cousins** (@cedric) · 2025-02-16 20:11

> **@nosle** (帖子 #41):
> All similar requiring between -30 and -40 ev compensation.

Please help me catch up - does “ev” mean stops, like in exposure compensation?!

---

## #49 **Andrea** (@arctic) · 2025-02-16 20:36

Welcome to pixls.us [@ChrisB](/u/chrisb)!

> **@ChrisB** (帖子 #46):
> convert it to png 16bit. This is the part I get confused: should I keep the transfer function “linear” or not ?

I usually export in PNG 16bit with the transfer function applied from darktable, then in the GUI I leave clicked the box “apply cctf decoding”. If you don’t export with the transfer function applied, leave unclicked the box “apply cctf decoding”.

The box “output cctf decoding” control if a transfer function is applied to the output image. Keep in mind that napari is not color managed and will always show an image as if it was sRGB (with transfer function). The underling data should nevertheless be in the right color space and cctf. I am borrowing all the color computations from the `colour-science` package.

> **@ChrisB** (帖子 #46):
> “compute full image”

As [@nosle](/u/nosle) commented this will make the program compute a full-res image. By default a downscaled preview is computed because the program is very slow for now (still faster than developing a real world RA4 test print strip

[![:yum:](https://discuss.pixls.us/images/emoji/apple/yum.png?v=12)](https://discuss.pixls.us/images/emoji/apple/yum.png?v=12)

).

> **@cedric** (帖子 #48):
> “ev” mean stops

Yes, you are correct.

---

## #50 **Ted Cousins** (@cedric) · 2025-02-16 21:03

> **@arctic** (帖子 #49):
> Ted Cousins:

“ev” mean stops

Yes, you are correct.

</blockquote>
</aside>

Interesting but puzzling … I calculate -30 EV to be a reduction factor of 9.3^(-10)

[![:hushed:](https://discuss.pixls.us/images/emoji/apple/hushed.png?v=12)](https://discuss.pixls.us/images/emoji/apple/hushed.png?v=12)

So I must be missing something. for example, on my monitor screen, it only takes -9 EV to get down from white to black. I do realize that my monitor brightness is not exposure. But still, Ansel Adams “scene” only spans 10 EV.

What am I not understanding?

---

## #51 **Andrea** (@arctic) · 2025-02-16 22:04

> **@cedric** (帖子 #50):
> Interesting but puzzling … I calculate -30 EV to be a reduction factor of 9.3^(-10)

It was a strange bug, possibly with overflowing of integers. Indeed 30ev is not normal, I usually set just a few stops of over or under exposure when using the simulation.

---

## #52 **Ted Cousins** (@cedric) · 2025-02-16 22:26

> **@arctic** (帖子 #51):
> Ted Cousins:

What am I not understanding?

It was a strange bug, possibly with overflowing of integers. Indeed 30ev is not normal, I usually set just a few stops of over or under exposure when using the simulation.

</blockquote>
</aside>

Got it. Thank you!

---

## #53 **** (@ChrisB) · 2025-02-17 13:21

Thanks for your answer !

I think my question is mostly about getting the input (png) in the expected state.

So (according to a few contacts of mine) I would need to do the following to convert my file :

- normalize
- convert gamut to Rec.709
- apply sRGB OECF

(Normalize as in expose down until the maximum value in your exr is equal to 1.0. A 16 bit png is an integer data type and therefore does not support pixel values greater than 1.0.)

I will try that as soon as possible. Thanks !

---

## #54 **Andrea** (@arctic) · 2025-02-17 16:21

Also make sure that, regardless of the transfer function (applied or not, and the corresponding checkbox clicked or not), your data is scene referred, i.e. the RGB values (without the transfer function) should be proportional to the amount of light that reached the camera sensor.

If other non-linear transformation were applied, the image will most likely look washed out. For example in darktable these are sigmoid, filmic, or base-curve. The simulation already applies a sigmoid filmic curve derived from real characteristic curve data, that assumes scene referred input.

> **@ChrisB** (帖子 #53):
> (Normalize as in expose down until the maximum value in your exr is equal to 1.0. A 16 bit png is an integer data type and therefore does not support pixel values greater than 1.0.)

Exact! Adjusting the exposure to not clip the PNG 16-bit range is also necessary.

---

## #55 **** (@ChrisB) · 2025-02-17 20:59

Thanks ! I think I got it working now.

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/2/52731fc95b8ad7177f6a537fc9e64c5cc9062b5d_2_690x387.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/2/52731fc95b8ad7177f6a537fc9e64c5cc9062b5d_2_690x387.jpeg)

image1703×956 278 KB](/uploads/short-url/bLnNUhNjqmmsSMiVvrN9Ryq5QaF.jpeg?dl=1)

Now I just need to render it in 20k

[![:wink:](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)

---

## #56 **Nate Weatherly** (@NateWeatherly) · 2025-02-17 22:29

Andrea. This is incredible. I’ve been trying to use density graphs, print emulation profiles/LUTs, custom profiles, commercial Davinci Resolve power grades, DCTLs, etc, etc, to come up with a linear digital → negative → print pipeline for years and the results with what you’ve made here are better than anything else I’ve seen. In the world of still photography software there is NOTHING else like this. I can’t speak to the technical “accuracy” of the emulation because I’ve never done analog RA-4 printing, but I can say that the results absolutely look like film in all the best ways.

In the short term, a couple requests for the sake of testing/experimentation… Is it possible to add more output color spaces? On a Mac, just having an ImageP3 or DisplayP3 output ICC profile would come pretty close to having a color managed preview. Also, a button to reset settings to the defaults would make experimenting easier.

For fun I tried to match a Noritsu film scan. I can’t remember what film it was, but the 400H + Fuji Crystal Archive comes really close. I tweaked the print gamma factor and then clipped to the black and white points which is what I assume was done to my film scan as well. Left is film, right is AGX:

[[![Screen Shot 2025-02-17 at 5.28.42 PM](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/a/aad5d3068dad0dfee217303d0af720b182cb49f0_2_690x371.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/a/aad5d3068dad0dfee217303d0af720b182cb49f0_2_690x371.png)

Screen Shot 2025-02-17 at 5.28.42 PM4144×2230 16.2 MB](/uploads/short-url/onhhLaYr2bLjuZok3Nv35f4E28o.png?dl=1)

---

## #57 **Andrea** (@arctic) · 2025-02-17 23:22

> **@ChrisB** (帖子 #55):
> Thanks ! I think I got it working now.

Great!

[![:star_struck:](https://discuss.pixls.us/images/emoji/apple/star_struck.png?v=12)](https://discuss.pixls.us/images/emoji/apple/star_struck.png?v=12)

 What kind of image is this? Is this a render you made, I am quite curious!

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

> **@ChrisB** (帖子 #55):
> Now I just need to render it in 20k

Soon we will able to do much larger resolutions! I am experimenting with moving the spectral calculations to intermediate LUTs, that should remove the memory bottleneck, and it should make the code more clear for GPU translation. Also, I am testing some small optimizations with Numba (totally new stuff for me) for faster grain synthesis.

So maybe not 20k, but hopefully 8k-6k easily.

[![:grin:](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)

---

## #58 **Andrea** (@arctic) · 2025-02-17 23:54

Thank you for the feedback [@NateWeatherly](/u/nateweatherly)!

> **@NateWeatherly** (帖子 #56):
> In the world of still photography software there is NOTHING else like this. I can’t speak to the technical “accuracy” of the emulation because I’ve never done analog RA-4 printing, but I can say that the results absolutely look like film in all the best ways.

I also think that still photography is somehow lacking in this kind of physically based simulations. There are a few options coming from video programs: for example [Dehancer](https://www.dehancer.com/shop/pslr/film) available also for Lightroom, Capture1 and Photoshop or [Filmbox](https://videovillage.com/filmbox/) but only for DaVinci resolve. But nothing truly dedicated to physically simulating still photography as far as I know. The ones I’ve seen somehow are always related to the movie industry or are less customizable profiles/LUTs (RNI and VSCO for example).

> **@NateWeatherly** (帖子 #56):
> having an ImageP3 or DisplayP3 output ICC

I just added DisplayP3 to the gui on the main branch. I couldn’t find ImageP3 in the `colour-science` [RGB color spaces](https://colour.readthedocs.io/en/master/generated/colour.RGB_to_RGB.html). Is ImageP3 the same as P3-D65?

> **@NateWeatherly** (帖子 #56):
> For fun I tried to match a Noritsu film scan. I can’t remember what film it was, but the 400H + Fuji Crystal Archive comes really close. I tweaked the print gamma factor and then clipped to the black and white points which is what I assume was done to my film scan as well. Left is film, right is AGX:

I love this comparison! Thank you for sharing. It is the kind of reference we need to bring the project forward and improve the results. The Noritsu scan is more green prominent and I don’t think it can be fixed in the virtual color enlarger. The dress and skin tones are impressively close!

Nice photo too! What kind of lens did you use for that swirly bokeh?

---

## #59 **Nate Weatherly** (@NateWeatherly) · 2025-02-18 02:10

> **@arctic** (帖子 #58):
> I also think that still photography is somehow lacking in this kind of physically based simulations. There are a few options coming from video programs: for example Dehancer available also for Lightroom, Capture1 and Photoshop or Filmbox but only for DaVinci resolve. But nothing truly dedicated to physically simulating still photography as far as I know. The ones I’ve seen somehow are always related to the movie industry or are less customizable profiles/LUTs (RNI and VSCO for example).

I haven’t tried Filmbox, but I played with sever versions of Dehancer and struggled to get results I liked. For whatever reason, the color in your transform is so much more pure and organic. Apparently VSCO has done a lot of research and work to measure profile film stocks and the Fuji Frontier scanner response, but their implementation in the app is so simple and limited that it really doesn’t matter.

All the Lightroom/C1 LUT profiles can do is emulate film at one exposure and scanner response and 3D LUTs just aren’t high enough resolution to map an “underexposed” linear image to the dynamic range of film like your transform does. The way you’ve implemented the auto exposure and exposure compensation for the negative and print is really smart. Can’t wait to see where this goes!

> **@arctic** (帖子 #58):
> I just added DisplayP3 to the gui on the main branch. I couldn’t find ImageP3 in the colour-science RGB color spaces. Is ImageP3 the same as P3-D65?

Thanks! That will be helpful. ImageP3 is basically the same thing as DisplayP3 as far as I can tell. Apple includes it with Mac OS and say it should be used with images, but I don’t see any difference. Display/Image P3 has the same primaries and white-point as P3-D65 but use the piecewise sRGB transfer function whereas P3-D65 uses gamma 2.6 like DCI-P3.

> **@arctic** (帖子 #58):
> I love this comparison! Thank you for sharing. It is the kind of reference we need to bring the project forward and improve the results. The Noritsu scan is more green prominent and I don’t think it can be fixed in the virtual color enlarger. The dress and skin tones are impressively close!

Yeah, I tried matching a few other images to film scans and the scans seemed to usually have more blue in the shadows. I was wondering if it might have something to do with film’s much stronger response in the deep blue/UV portion of the spectrum compared to digital cameras and spectrometers? Maybe there’s some way to optionally add UV exposure to the sRGB spectral reconstruction?

> **@arctic** (帖子 #58):
> Nice photo too! What kind of lens did you use for that swirly bokeh?

Thanks! I’m not 100% certain, but I think it was a Leica Summilux 35mm FLE. I think the swirls happened because I wasn’t thinking and was using it on a Techart pro AF adapter, meaning the floating element wasn’t being adjusted for the distance. Also just using the rangefinder glass on a Sony sensor does some of that.

Oh, question regarding white balance—should the linear digital image be white balanced to make a neutral image, or set to 5500K to match film’s native response?

---

## #60 **Bob** (@PhotoPhysicsGuy) · 2025-02-18 12:21

> **@arctic** (帖子 #57):
> What kind of image is this?

Not sure if it helps, but there are/were a bunch of pictures (synthetic and real world) which came up regularily in the ACES2.0 workgroup iirc this one as well. These reference pics served as a wide variety of inputs to test DRT implementations.

Also there are some *spectral* renders in that workgroup, specifically the cornell box illuminated by spectrally pure wavelengths including exposure ramps!

I would love to see how all of those pictures look through “agx-emulsion”. But I don’t know how easy it is to get those pics from the workgroup.

But maybe [@ChrisB](/u/chrisb) can elaborate on this.

A good read:

[ACES 2.0 Workgroup DRT dev thread.](https://community.acescentral.com/t/aces-2-0-cam-drt-development/4700)

---

## #61 **Paul Matthijsse** (@paulmatth) · 2025-02-18 14:25

Hello, problem opening files on Xubuntu 24.04 with 8GB RAM (too low on RAM perhaps?).

I followed the installation instructions on Github, using conda. Everything installs fine and the program starts. But when I drag a photo on the application, nothing opens/happens. Instead there are error messages in the console.

```
(agx-emulsion) paul@graveyron:~/apps/agx-emulsion$ python agx_emulsion/gui/main.py
MESA-LOADER: failed to open nouveau: /usr/lib/dri/nouveau_dri.so: kan gedeeld objectbestand niet openen: Bestand of map bestaat niet (search paths /usr/lib/x86_64-linux-gnu/dri:\$${ORIGIN}/dri:/usr/lib/dri, suffix _dri)
failed to load driver: nouveau
MESA-LOADER: failed to open nouveau: /usr/lib/dri/nouveau_dri.so: kan gedeeld objectbestand niet openen: Bestand of map bestaat niet (search paths /usr/lib/x86_64-linux-gnu/dri:\$${ORIGIN}/dri:/usr/lib/dri, suffix _dri)
failed to load driver: nouveau
MESA-LOADER: failed to open swrast: /usr/lib/dri/swrast_dri.so: kan gedeeld objectbestand niet openen: Bestand of map bestaat niet (search paths /usr/lib/x86_64-linux-gnu/dri:\$${ORIGIN}/dri:/usr/lib/dri, suffix _dri)
/home/paul/apps/agx-emulsion/agx_emulsion/gui/main.py:24: FutureWarning: Public access to Window.qt_viewer is deprecated and will be removed in
v0.6.0. It is considered an "implementation detail" of the napari
application, not part of the napari viewer model. If your use case
requires access to qt_viewer, please open an issue to discuss.
 layer_list = viewer.window.qt_viewer.dockLayerList
WARNING: QOpenGLWidget: Failed to create context
WARNING: QOpenGLWidget: Failed to create context
WARNING: composeAndFlush: QOpenGLContext creation failed
WARNING: composeAndFlush: makeCurrent() failed
WARNING: composeAndFlush: makeCurrent() failed
WARNING: composeAndFlush: makeCurrent() failed

```

Here the program hangs.

Seems that the nouveau driver can’t be found. On my system it is not in /usr/lib/dri (that folder does not exist). A `locate nouveau ` shows the following: /usr/lib/xorg/modules/drivers/nouveau_drv.so.

Following is the output of inxi -G

```
(agx-emulsion) paul@graveyron:~/apps/agx-emulsion$ inxi -G
Graphics:
 Device-1: NVIDIA GT218 [GeForce 210] driver: nouveau v: kernel
 Display: x11 server: X.Org v: 21.1.11 driver: X: loaded: modesetting
 unloaded: fbdev,vesa dri: nouveau gpu: nouveau resolution: 1920x1080~60Hz
 API: EGL v: 1.4,1.5 drivers: nouveau,swrast
 platforms: x11,surfaceless,device
 API: OpenGL v: 4.5 compat-v: 3.3 vendor: mesa v: 24.0.9-0ubuntu0.1
 renderer: NVA8

```

Any ideas?

---

## #62 **Paul Matthijsse** (@paulmatth) · 2025-02-18 14:42

OK, so I copied /usr/lib/xorg/modules/drivers/nouveau_drv.so to /usr/lib/dri (folder created) and renamed the driver to nouveau_dri.so.

I start the program and now there’s another error msg:

```
(agx-emulsion) paul@graveyron:~/apps/agx-emulsion$ python agx_emulsion/gui/main.py
MESA-LOADER: failed to open nouveau: /usr/lib/dri/nouveau_dri.so: undefined symbol: xf86CrtcConfigPrivateIndex (search paths /usr/lib/x86_64-linux-gnu/dri:\$${ORIGIN}/dri:/usr/lib/dri, suffix _dri)
failed to load driver: nouveau
MESA-LOADER: failed to open nouveau: /usr/lib/dri/nouveau_dri.so: undefined symbol: xf86CrtcConfigPrivateIndex (search paths /usr/lib/x86_64-linux-gnu/dri:\$${ORIGIN}/dri:/usr/lib/dri, suffix _dri)

```

---

## #63 **Andrea** (@arctic) · 2025-02-18 20:45

I haven’t tried Dehancer (or Filmbox), just admired the gorgeous examples they have on the website and some videos on Youtube.

[![:star_struck:](https://discuss.pixls.us/images/emoji/apple/star_struck.png?v=12)](https://discuss.pixls.us/images/emoji/apple/star_struck.png?v=12)

 Since they want to run on video, I guess they have different priorities for overall computational efficiency. I think the simulation in `agx-emulsion` is not true because it is not based on real profiled scans. There is a lot of reasonable guessing. At the same time it is a physically based model end to end, so it might be more “robust” and “smooth” in more edge conditions, i.e. it might fail more smoothly.

> **@NateWeatherly** (帖子 #59):
> Yeah, I tried matching a few other images to film scans and the scans seemed to usually have more blue in the shadows. I was wondering if it might have something to do with film’s much stronger response in the deep blue/UV portion of the spectrum compared to digital cameras and spectrometers? Maybe there’s some way to optionally add UV exposure to the sRGB spectral reconstruction?

I was thinking of adding a “tint” control for the toe region of the negative, this should add some flexibility for toning the shadows independently. Also it should be able to control the color of very underexposed negatives, that can change quite a lot (just looking at example online) and I guess depends from the development conditions. It’s in my todo list.

> **@NateWeatherly** (帖子 #59):
> Oh, question regarding white balance—should the linear digital image be white balanced to make a neutral image, or set to 5500K to match film’s native response?

That’s a good question. At the beginning I was always correcting the white balance with darktable. Recently I started fixing the white balance at 5500K and I do like the results, e.g. sunset shots for example that I tend to leave warmer in this way. I haven’t done a serious comparison, but I suspect that subtle differences should be present due to the crosstalk in the enlarger filtering and paper absorptions (not precise as the digital wb). Plus it sounds more correct.

Kodak and Fuji apparently are balanced for 5500K and 6500K respectively. I don’t have a good reference to support that, but this is what I am using in the spectral up-sampling from sRGB. The algorithm from [Mallett2019] should work very well only for 6500K and just ok for 5500K, not well for lower temperatures. Tungsten balanced film will have to wait a better up-sampling alg implementation. **I still tend to use 5500K as a default wb for the input.**

---

## #64 **Andrea** (@arctic) · 2025-02-18 20:52

> **@PhotoPhysicsGuy** (帖子 #60):
> A good read:
ACES 2.0 Workgroup DRT dev thread.

Thanks! That thread is impressively stimulating to scroll, there is so much nice visualization and color science at play. I am kind of shocked

[![:face_with_spiral_eyes:](https://discuss.pixls.us/images/emoji/apple/face_with_spiral_eyes.png?v=12)](https://discuss.pixls.us/images/emoji/apple/face_with_spiral_eyes.png?v=12)

 I will have a read.

> **@PhotoPhysicsGuy** (帖子 #60):
> Not sure if it helps, but there are/were a bunch of pictures (synthetic and real world) which came up regularily in the ACES2.0 workgroup iirc this one as well. These reference pics served as a wide variety of inputs to test DRT implementations.

Having images that can show problems would be great! I am pretty sure we will find many issues.

[![:grin:](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)

 I will look for those images, but of course, I will be happy to be pointed to the repo if you know where to find them [@ChrisB](/u/chrisb).

---

## #65 **Andrea** (@arctic) · 2025-02-18 20:58

It looks like a GPU driver problem that should be independent from `agx-emusion` (that does not use GPU). napari is gpu-accellerated as far as i know. Try to run napari independently, from the terminal run this:

```
> conda activate agx-emulsion
> napari

```

And try to load the same image. If you have the same problem I am afraid I am not the most knowledgeable person to find a solution for this. Maybe write me a direct message if you have more info, so we leave this thread more free for discussions.

---

## #66 **** (@ChrisB) · 2025-02-18 22:45

This is indeed a render that I provided for the ACES 2.0 working group.

You may find the images here:

- [Output Transform Image Submissions](https://www.dropbox.com/scl/fo/fhzx0bcwcjylek1oz7kjc/ACGfmi0EHeufVOQPZLvvk7w?rlkey=53cp61955hbns8x46j6cf8k55&e=1&dl=0) (most of them encoded in ACES2065-1)
- [Gralk Git](https://github.com/gralk/images) (encoded in linear - eGamut)
- [ACES ODT Sample Frames](https://github.com/ampas/ACES_ODT_SampleFrames) - (encoded in ACES2065-1 I think)

Here is another example:

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/b/5bac5ec7d9aba20a735ba49709c4bab0d3ac80b1_2_690x294.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/b/5bac5ec7d9aba20a735ba49709c4bab0d3ac80b1_2_690x294.jpeg)

image1306×558 195 KB](/uploads/short-url/d4YKA9rSKzv53h6DjNe1QgP2veN.jpeg?dl=1)

About the ACES 2.0 thread (CAM DRT), I would “take it” carefully. The use of Color Appearance Model in image formation is highly debatable to say the least.

---

## #67 **Paul Matthijsse** (@paulmatth) · 2025-02-19 09:22

> **@arctic** (帖子 #65):
> Maybe write me a direct message

Done.

---

## #68 **Andrea** (@arctic) · 2025-02-19 19:32

> **@ChrisB** (帖子 #66):
> You may find the images here:

Thank you for the links!

[![:smiley:](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)

 I’ll experiment with them. They are going to be useful, since I will expand the input color space to larger ones.

Nice Lego render. Do you think the Lego figurine in the background has some red gradient issues? Or is this image used to reveal anything in particular?

---

## #69 **jo** (@hanatos) · 2025-02-19 20:28

> **@arctic** (帖子 #68):
> I will expand the input color space to larger ones.

about that

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 where would that have to happen? my current understanding of the code is that it would be one of the first steps of the film code, where the input image is converted to linear light rgb and then passed through the density look up table to give cmy densities. i think this is the profile that is precomputed in the longish json files… (i think i want these as a lookup texture) how/where do you compute it? i’m assuming internally it has a linear rgb → spectrum → density of turned grains pipeline?

i would probably just use a simple full-gamut sigmoid emission upsampling method for rgb to spectrum out of srgb. this requires a simple 2D lut from xy chromaticity to coefficients for the parametric spectra (can provide lut). some more broken/matrix-based input device transforms would give you rgb values for the input image that are even way out of spectral locus. i’ve seen some of that in the aces thread. we can’t upsample these coordinates, they’ll need to be clamped to real stimuli first (don’t want negative energies on some wavelengths).

---

## #70 **Andrea** (@arctic) · 2025-02-19 23:47

Right now, I am optimizing the pipeline to make it more clear and efficient. If anything looks stupid please don’t hesitate to say that.

I confined all the spectral calculations in three LUTs (3D LUT 1, 2, and 3).

I can now compute 100MP images without running out of RAM! Still ages to compute.

[![:joy:](https://discuss.pixls.us/images/emoji/apple/joy.png?v=12)](https://discuss.pixls.us/images/emoji/apple/joy.png?v=12)

[[![gold200_portra_default_84MP](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/e/fee9dd09f3c3ebdd33c54fe716f6b977225a84cb_2_100x150.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/e/fee9dd09f3c3ebdd33c54fe716f6b977225a84cb_2_100x150.jpeg)

gold200_portra_default_84MP7506×11268 12.7 MB](/uploads/short-url/An4kjfylTR7KU7SDqU5fTFZvoH9.jpeg?dl=1)

(sorry the huge image, I compressed a lot though)

And thank you [@Artaga734](/u/artaga734) for helping with some profiling of the code!

I am attaching a small scheme of the pipeline that might make things more clear than my dirty code. I specified input-outputs of the LUTs. All variables are 3 channel images.

[[![agx-emulsion_pipeline_0.2.0](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/0/30c33c6e7f34ecc182d9c9ee890112a85d6e726c_2_690x858.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/0/30c33c6e7f34ecc182d9c9ee890112a85d6e726c_2_690x858.png)

agx-emulsion_pipeline_0.2.01933×2405 382 KB](/uploads/short-url/6Xnd0UcadiZ0sBOLsGxbSm5hQzq.png?dl=1)

You can clearly see the two step of the imaging system (film + print). The 3D LUTs are covering the spectral calculations happening in the camera, enlarger, and scanner (or I guess more precisely in our eyes). I think that some magic happens in 3D LUT2 and 3D LUT3 where there is subtle crosstalk among the channels and the spectral density saturates smoothly, slowing eating away the light around the absorption peaks of the dyes.

> **@hanatos** (帖子 #69):
> my current understanding of the code is that it would be one of the first steps of the film code, where the input image is converted to linear light rgb

Exactly! It is going to be at the very beginning of the pipeline. I am converting input image >> linear rgb >> spectral upsampling x film sensitivities >> exposure of each layer of the film (3 channels).

And you are right that 3D LUT1 could become 2D using only xy chromaticities. I didn’t think about that!

[![:smiley:](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)

 Is this a standard way of doing things?

> **@hanatos** (帖子 #69):
> i would probably just use a simple full-gamut sigmoid emission upsampling method for rgb to spectrum out of srgb. this requires a simple 2D lut from xy chromaticity to coefficients for the parametric spectra (can provide lut).

That would be great actually! I don’t know the “full-gamut sigmoid emission upsampling” method, do you have a reference? And is this what you would recommend for best quality results? I was also playing a bit with [colour.recovery.LUT3D_Jakob2019](https://colour.readthedocs.io/en/latest/generated/colour.recovery.LUT3D_Jakob2019.html) to precompute spectra in a 3D LUT to be stored and used in 3D LUT1 (this is still yours

[![:grin:](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)

, I glanced the paper and it is an amazing piece of work). Do you think that it is an overkill solution?

Also I noticed that in *Jakobs2019* the spectra can change quite a lot at extreme values of lightness (10^-4 and close to 1). For example I was calculating the spectra for al the possible values of the ACES2065-1 space in a grid 32x32x32 (that might be dumb). I was limiting the values between 0 and 0.1 in 32 steps. I restricted to 0.1 because values closer to 1 were broadening quite a lot the narrower spectra. Is this a limitation of the method or somehow intended?

---

## #71 **Alberto** (@agriggio) · 2025-02-20 06:19

(TL;DR: just a *huge thanks* from me too! For more, keep reading at your own risk

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

Hi,

I just wanted to join the crowd of fans of this awesome project. I have been playing with it for the past 10 days, essentially since the moment it was announced. I am continuously amazed by how easy it is to get great results. Kudos [@arctic](/u/arctic)!

So, I immediately started thinking about how to incorporate this into my workflow. The code is way too complex to just “borrow/steal” it, and it requires a level of knowledge of the whole film processing pipeline that I simply do not have (though the diagram above helps quite a lot in getting the big picture).

At first, I tried to see whether I could match the renderings with more conventional digital tools for tonemapping and colour grading. Well, yes, you can get close, but it’s quite a bit of work, and the closer you get, the more fragile the “standard digital” way becomes (meaning: you might get close for a particular picture, but getting something robust seems much harder).

Therefore, I started thinking of another way, and I now have something that I consider good enough for my purposes. Basically, I managed to extend ART’s support for 3dLUT plugins to allow it to use “externally computed 3dLUTs”, that can run arbitrary code to compute a LUT in CLF format, and then use it in the ART pipeline. After a bit of boilerplate (really, just a couple of hours of coding), I managed to get something working. I can now enjoy the awesomeness of [@arctic](/u/arctic)’s work (*) inside ART – and this makes me smile

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

Here’s a little demo just to prove I’m not making things up:



(As you can see, it takes some time to (re)compute the LUT after changing settings, but (a) this is cached so reapplying the same settings is then fast, and (b) my laptop is really getting old now…)

(*) NOTE: this only works for the “tone mapping” part of AgX-emulsion; I had to turn off all the spatial processing (e.g. grain, halation, and other diffusion-based processes). This is not a big deal *for me*, since I was mostly interested in the tonemapping stuff, and ART has some (way less accurate and convincing, but still) other way of faking grain and halation. But definitely something to keep in mind.

---

## #72 **jo** (@hanatos) · 2025-02-20 08:38

awesome, thanks for the schematic, that helps a lot indeed! initially i thought i’d have to store spectral frame buffers as intermediates and was thinking of ways to compress them, but that doesn’t seem to be the case, so that’s great. about the spectral upsampling stuff:

> **@arctic** (帖子 #70):
> And you are right that 3D LUT1 could become 2D using only xy chromaticities. I didn’t think about that! Is this a standard way of doing things?

no, usually we do 3D, because there is a joint limit on how saturated and how bright a reflectance spectrum can be (mac adams limit, can’t reflect more than 100% in each wavelength, so more colourfulness means less reflectance/darker). this means the spectral shape has more freedom for darker reflectances and it’s important to include that in an upsampling algorithm.

now we’re dealing with *emission* i.e. unbounded signals here, not *reflectances*.

by “full gamut sigmoid emission upsampling” i meant [Jakob 2019] (the sigmoid part), but with a lut that spans the whole spectral locus (full gamut). also it should be for emission, not for reflectances. this is not a natural match to bounded sigmoids, but we can always scale the overall energy up, keeping the shape. what i’ve done in the past is use a 2D table on xy chromaticities (or something similar directly in 2d/rec2020 because that’s my working space), and do sigmoid upsampling at some medium brightness, and then scale the spectrum up to match the energy of the input signal.

> **@arctic** (帖子 #70):
> For example I was calculating the spectra for al the possible values of the ACES2065-1 space

how did you do this? does the `colour` code only read the precomputed coef files or run the gauss/newton optimiser? the sigmoidal function class here can represent spectra pretty much all the way to the end… but that’s the end of the spectral locus/mac adams limit. ACES AP0/2065-1 is pretty much XYZ with the red corner cut off for better looks: [https://facelessuser.github.io/coloraide/images/aces2065-1.png](https://facelessuser.github.io/coloraide/images/aces2065-1.png)

that means there are some values outside spectral locus that require imaginary stimuli/don’t have a valid spectral power distribution as representation. maybe you ran into this region?

---

## #73 **Andrea** (@arctic) · 2025-02-20 16:05

Hey [@agriggio](/u/agriggio)! Really appreciate this message and your work. That was very fast! I like how you distilled the essentials in the GUI, with all the basics needed for the tonemapping. Great job!

[![:grinning:](https://discuss.pixls.us/images/emoji/apple/grinning.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grinning.png?v=12)

> **@agriggio** (帖子 #71):
> I am continuously amazed by how easy it is to get great results.

I am also in a way learning from the output of the simulations. It is shaping my tastes, and looking back at images I processed before, it showed me that sometimes I should dare more with contrast and saturations (but in the right “ways”), and the simulation is selecting the right colors palettes that do this comfortably. I guess that investigating how the LUTs are actually shaping the colors might give some general insight, to develop generic and efficient tools that mimics the simulations output.

> **@agriggio** (帖子 #71):
> (*) NOTE: this only works for the “tone mapping” part of AgX-emulsion; I had to turn off all the spatial processing (e.g. grain, halation, and other diffusion-based processes). This is not a big deal for me, since I was mostly interested in the tonemapping stuff, and ART has some (way less accurate and convincing, but still) other way of faking grain and halation. But definitely something to keep in mind.

My interest in grain simulations was my gateway into this project, but this makes also total sense.

[![:blush:](https://discuss.pixls.us/images/emoji/apple/blush.png?v=12)](https://discuss.pixls.us/images/emoji/apple/blush.png?v=12)

As a side note, I think that to be more true to the analog film+printing system, I would change the print gamma and keep the film gamma untouched if possible. This makes also more sense because of how DIR couplers works based on the density values in the film.

---

## #74 **Andrea** (@arctic) · 2025-02-20 16:32

> **@hanatos** (帖子 #72):
> no, usually we do 3D, because there is a joint limit on how saturated and how bright a reflectance spectrum can be (mac adams limit, can’t reflect more than 100% in each wavelength, so more colourfulness means less reflectance/darker). this means the spectral shape has more freedom for darker reflectances and it’s important to include that in an upsampling algorithm.
now we’re dealing with emission i.e. unbounded signals here, not reflectances.

Indeed that makes a lot of sense, thanks for the clarification!

> **@hanatos** (帖子 #72):
> how did you do this? does the colour code only read the precomputed coef files or run the gauss/newton optimiser?

The `colour` package can do both. Recall the LUT of precomputed coefficients from the supplementary of [Jakob2019], run the optimizer (with a much greater computational cost), or also compute a new LUT if needed. I was definitely comparing spectra in the imaginary region. This is what I had, exactly on the edge beyond the green side of the visual locus.

I got this spectra from the LUT of coefficients:

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/8/4/84943a99f6a3fff84898d387e8034d07f791a2b9.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/8/4/84943a99f6a3fff84898d387e8034d07f791a2b9.png)

image580×455 57.6 KB](/uploads/short-url/iUQBvV3SJ4fwmjbwDeNtDsZaRjb.png?dl=1)

<details>
<summary>
Code</summary>

<pre data-code-wrap="python"><code class="lang-python">import numpy as np
import colour
import colour_datasets
import matplotlib.pyplot as plt

LUT_SIZE = 32
RGB_MAX_VALUE = 0.2

lut_aces = colour_datasets.load("4050598")['ACES2065-1']
spectral_shape = colour.SpectralShape(380, 780, 5)
wl = spectral_shape.wavelengths
x = np.linspace(0.0,1.0,LUT_SIZE)

lut_spectra = np.zeros((LUT_SIZE, LUT_SIZE, LUT_SIZE, np.size(wl)))
for i in np.arange(LUT_SIZE):
 for j in np.arange(LUT_SIZE):
 for k in np.arange(LUT_SIZE):
 rgb = np.array([x[i],x[j],x[k]]) * RGB_MAX_VALUE
 sd = lut_aces.RGB_to_sd(rgb, spectral_shape)
 lut_spectra[i,j,k,:] = sd[:]
 print('Fraction computed:',(i+1)/LUT_SIZE)

plt.plot(wl,lut_spectra[0,:,0,:].transpose())
plt.ylim((0,1))
plt.xlabel('Wavelegth (nm)')
plt.ylabel('Reflectance')
plt.title('ACES2065-1 - RGB=[0,x,0] - x_range=[0,0.2]')
</code></pre>

</details>

And this example from the solver:

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/9/a/9a8e35cf8c407b61f2a6d5b71c6ad03344eefc7a.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/9/a/9a8e35cf8c407b61f2a6d5b71c6ad03344eefc7a.png)

image580×455 16.6 KB](/uploads/short-url/m3gdi7Zmd1FQia7LF8cUzTnPtX4.png?dl=1)

<details>
<summary>
Code</summary>

<pre data-code-wrap="python"><code class="lang-python">import numpy as np
import matplotlib.pyplot as plt
import colour

rgb = np.array([0.00,0.05,0.00])
xyz = colour.RGB_to_XYZ(rgb, colourspace='ACES2065-1')
out, _ = colour.recovery.find_coefficients_Jakob2019(xyz)
sd = colour.recovery.sd_Jakob2019(out, colour.SpectralShape(380, 780, 5))

plt.plot(sd.wavelengths, sd[:])
plt.ylim([0, None])
plt.xlabel('Wavelength (nm)')
plt.ylabel('Reflectance')
plt.title('ACES2065-1 - RGB=[0,0.05,0]')
</code></pre>

</details>

The solver is sharper but I guess we shouldn’t care much about this region.

---

## #75 **Jed Smith** (@jedsmith) · 2025-02-21 05:09

Hi [@arctic](/u/arctic)

I just wanted to chime in as well and say really nice work on this project. I’ve been tinkering with it and am really impressed and intrigued with the approach.

Expanding on [@ChrisB](/u/chrisb)’s [reply](https://discuss.pixls.us/t/spectral-film-simulations-from-scratch/48209/53) above, I was wondering if you had any interest in adding `exr` as an input image format? In addition to being a generally terrible image format, `png` is really not designed to encode “scene-referred” pixel data. Multiplying down a “scene-linear” image and encoding it as a 16 bit linear exr is incredibly inefficient and poor quality due to the way the quantization works (16 bits distributed linearly over a 0-1 range on a multiplied down “scene-linear” image will put most of the image data in the lowest region, resulting in fewer bits of precision to encode the data). Another workaround might be to add some “scene-referred” transfer functions to encode the image data in a log encoding and store that as a 16 bit png. But now that openimageio is available as a python wheel and installable with `uv` / `pip`, maybe it’s worth investigating exr support?

Happy to help if I can when I get some spare time!

Again, thanks for the great work, excited to play with this more.

---

## #76 **Andrea** (@arctic) · 2025-02-21 12:49

Hey [@jedsmith](/u/jedsmith), I am glad you manage to play with it! Thank you for the comment.

Listening also to the feedback from [@ChrisB](/u/chrisb) and [@liam_collod](/u/liam_collod), I just added to the main branch a few updates, including the possibility to load `exr` files (32bit and 16bit). I am using now OpenImageIO as recomended, and I dropped the need of downloading the freeimage backend. I quickly tested and seems to work fine, but if you test with more exr files let me know how it goes.

The main branch has now also a few optimization for accelerating the grain synthesis with some `numba` functions, and all the spectral calculations are now behind 3D luts. The memory bottlenecks should also be drastically reduced.

I updated the requirements with the new packages. I had to revert to a slightly older version of `numpy` for compatibility with `numba`.

The input color space can also be different than sRGB, but it will be internally converted to sRGB and clipped at the very beginning of the pipeline to use [Mallett2019] spectral upsampling. The color space must be selected in the input tab. Larger spaces are coming (WIP).

---

## #77 **Jakob Andrén** (@jandren) · 2025-02-21 18:21

Nice then I don’t need to make a PR with my .exr implementation that I did this morning!

Definitely a workflow improvement to use linear .exr files, makes it possible to adjust the exposure in darktable with sigmoid activated and then just deactivate at time of export. Just load and deactivate “input/apply cctf encoding”, no auto exposure required!

I have to confess as being one of the pure tone mapping users atm but that is really interesting enough. Can’t really say much about the correctness of it all at this point more than that it looks good and that I love the first principles approach. Looking forward to digging deeper into this, especially wider gamut inputs and how that handle later.

I love charts as a complement to images so here is the result using the syntheticChart.01 from [ACES](https://acescentral.com/knowledge-base-2/using-aces-reference-images/).

[[![Simulation result ACES chart](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/5/2503c76ad7043d72889dae7337d88d3a2e1928b7_2_690x363.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/5/2503c76ad7043d72889dae7337d88d3a2e1928b7_2_690x363.jpeg)

Simulation result ACES chart2048×1080 196 KB](/uploads/short-url/5hrLihCme9XHRlzPWdDZbiVkezl.jpeg?dl=1)

kodak_gold_200 + kodak_endura_premier

No auto exposure/compensation or other variations from defaults other than disabling all spacial effects and grain.

The horizontal bars in the middle are zero at the center and negative towards the right so something goes wrong with “negative” colors.

Some colors that desaturates later but not as bad as normal per-channel methods would do if you just clipped the gamuts to their boarders.

---

## #78 **Liam Collod** (@liam_collod) · 2025-02-21 20:32

Cool update ! It allowed me to test some film comparison assets I had:
<aside class="onebox allowlistedgeneric" data-onebox-src="https://mrlixm.github.io/assets/chkpad1/">
 <header class="source">


[![图片128](https://d2x313g9lpht1q.cloudfront.net/original/3X/7/3/73b3848f9f3adea2109c8d2c87f9c73a0a1e82d5.svg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/7/3/73b3848f9f3adea2109c8d2c87f9c73a0a1e82d5.svg)

 [Liam Collod Website](https://mrlixm.github.io/assets/chkpad1/)
 </header>

 <article class="onebox-body">


[![图片129](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/c/acab4d5666e9b217c619c99082209ae583777665_2_690x411.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/c/acab4d5666e9b217c619c99082209ae583777665_2_690x411.png)

### [film-vs-digital asset chkpad1](https://mrlixm.github.io/assets/chkpad1/)


assets for comparison of film photography rendering against arbitrary digital photography rendering

 </article>









</aside>

I can’t say the scene composition is the most appropriate to showcase color rendition as it’s pretty bland but I think it’s interesting nonetheless.

So I ran the digital source exr through the sim and got this:

[[![2025_02_21_210148_2481x914](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/8/e8badb50851566a5b8998ace0120fb1132094824_2_690x254.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/8/e8badb50851566a5b8998ace0120fb1132094824_2_690x254.jpeg)

2025_02_21_210148_2481x9142481×914 269 KB](/uploads/short-url/xcP6VEoqON1kXW3CqA6HyiNUSSE.jpeg?dl=1)

- left is the film ref that have been subjectively tweaked and generated using [my personal film scanning workflow](https://youtu.be/0H__azbRYPw); note I had to increase the saturation on the film ref by +1.25 using “max luminance math” as it was pretty bland and hard to compare with the sim.
- right is the result of the sim using the digital source images with sRGB primaries (I reconverted the provided BT.2020 exr to be safe). I reduced the dir couplers again to try to match the saturation of the film ref.

So there is a lot of bias and issues in that comparison but straightaway I think I can notice the bottom cyan patch to completely explode which is very interesting.

As this patch issue rings a bell I decided to run a second test:

[[![2025_02_21_211358_2317x913](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/f/3f9214ac0cb445f42afe6a321212827f23c36588_2_690x271.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/f/3f9214ac0cb445f42afe6a321212827f23c36588_2_690x271.png)

2025_02_21_211358_2317x9132317×913 1.69 MB](/uploads/short-url/94n3xSUxspjOXBjuTT0XUF9CP44.png?dl=1)

- same ref on the left (EDIT: **please ignore left image**, it’s the digital with an arbitrary image formation, use ref on previous picture sry)
- on the right I I now used the digital source that have been debayered to the native camera colorspace instead (file not provided, I did it on my side), and then just interpreted as sRGB in the film-sim app; basically skipping all colourimetric transformations. To compensate I had to increase the dir couplers amount this time.

Now we can see that the blue patch doesn’t explode anymore and the overall tones feels closer to the film ref.

<hr>

I can’t conclude much with that little experiment but to raise the issue that source image encoding and decoding also seems to play an important role to get the whole image formation pipeline closer to analogue film.

---

## #79 **jo** (@hanatos) · 2025-02-22 07:56

> **@arctic** (帖子 #74):
> The solver is sharper

hmm i think 32 cubed might not be super high res… maybe the discretisation near the edge changes the result a lot. another thing to consider is the limits of the gamut. these bounded spectra fall inside MacAdams limit, i.e. can’t go to negative energies (outside spectral locus, sideways) and can’t be too bright (reflectances are <=100%). i think in the huge AP0 gamut you’d encounter both limits. the optimiser may or may not diverge in such cases.

but yes, see pm for special cased upsampling code, hope to see it upstream soon

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

---

## #80 **Andrea** (@arctic) · 2025-02-22 14:12

Nice [@jandren](/u/jandren)!

> **@jandren** (帖子 #77):
> Can’t really say much about the correctness of it all at this point more than that it looks good and that I love the first principles approach.

Indeed, I also am afraid that true film simulation of the output of real film stock is probably impossible just with first principle. Some kind of real reference is necessary to understand better. Maybe one could think to fit part of the model to some real data. I think it is better to say that the output is somehow inspired by a film-stock/print-paper data within the limit of the model.

> **@jandren** (帖子 #77):
> The horizontal bars in the middle are zero at the center and negative towards the right so something goes wrong with “negative” colors.

I don’t get much this part about the negative colors. I found this [page](https://community.acescentral.com/t/aces-synthetic-chart/4600/2) where they describe the rationale of this test image. But what do the negative colors should show about the tone mapping pipeline?

---

## #81 **Andrea** (@arctic) · 2025-02-22 14:56

This is definitely super interesting [@liam_collod](/u/liam_collod), thanks for sharing this asset.

I think it is quite a controlled comparison.

Also I watched you video on film inversion with Nuke, very cool! I am especially intrigued by your decision on using the camera color space without conversion. Indeed it sounds a robust way to avoid any negative values that are not physically possible.

> **@liam_collod** (帖子 #78):
> So there is a lot of bias and issues in that comparison but straightaway I think I can notice the bottom cyan patch to completely explode which is very interesting.

I also notice the cyan explosion in some tests, but still haven’t addressed or pinpointed the root causes. As you demonstrated with your experiment it is most likely relatedto the spectral upsampling of RGB data. From some discussion with [@hanatos](/u/hanatos), I suspect that this is partially related to the fact that upsampling algs are optimized to minimize the errors when XYZ sensitivities are applied. Film negative sensitivities can be quite different from the standard observer. This is for example of Kodak Portra 400:

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/9/4/944242fd835440268106abf6fdcfebd49c21db60.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/9/4/944242fd835440268106abf6fdcfebd49c21db60.png)

image569×455 42.2 KB](/uploads/short-url/l9yD674ZCG3QSDFqGHkdoQWk31m.png?dl=1)

The film absorbs much wider and with less overlapping sensitivities. My reasonng is that upsampled spectra from RGB do not impose good constraints on the region of the spectrum outside XYZ sensitivities. So the generated spectra might have not reasonable values at the edge of the visible spectrum where film absorbs and eyes do not. But I am not the most knowledgeable on the topic to elaborate deeply on it. I will need to spend some more thoughts on this.

> **@liam_collod** (帖子 #78):
> on the right I I now used the digital source that have been debayered to the native camera colorspace instead (file not provided, I did it on my side), and then just interpreted as sRGB in the film-sim app; basically skipping all colourimetric transformations. To compensate I had to increase the dir couplers amount this time.

This little experiments, even with all it’s limitations, really tickles my brain, and it will trigger some nice thoughts and discussion I think! Thank you for sharing!

[![:grinning:](https://discuss.pixls.us/images/emoji/apple/grinning.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grinning.png?v=12)

I would say that the way we decode the image from the raw, and they way it enters the spectral pipeline has a huge impact.

---

## #82 **jo** (@hanatos) · 2025-02-22 15:08

… if i were to bake stuff into images as luts. the profile json, are they all the same shape/wavelength range? i’m thinking i could make one image for say log_sensitivities, where each row would be one film stock. but that would only be a good idea if these are generally all the same and only the data is different.

---

## #83 **Andrea** (@arctic) · 2025-02-22 15:24

All the spectral data are represented on the same wavelength axis (N wavelength data points). Depending on the version 380-780 every 10 nm, or 380-780 every 5 nm. I am keen to stay with the 5 nm representation, that was the optimum that I found early on.

Spectral data are:

- film log-sensitivities (`log_sensitivity`): array Nx3 for RGB layers
- dye density absorption spectra (`dye_density`): array Nx5 for [C,M,Y,minimum density, medium neutral density]
 Note: medium neutral density is not really needed. It is only used in the making of the profiles.

There are then density characteristic curves data, all represented on a log-exposure scale (M points), quite oversampled since later I am using linear interpolation on them.

There are:

- characteristic curves of the layers (`density_curves`): Mx3 for RGB channels
- characteristic curves of each sub layer (`density_curves_layers`): Mx3x3 for [log-exposure, sublayer, rgb-layer], used for the multi layer grain synthesis

---

## #84 **jo** (@hanatos) · 2025-02-23 11:31

thanks for all your explanations! i think i got very many details wrong, and i’m ignoring all the normalisations and illuminants involved in making the image… but i cat at least get recognisable pixels now:

[[![20250223_12h27m28s_grim](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/2/222826471675701b67de54c369f176039b1e2485_2_690x657.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/2/222826471675701b67de54c369f176039b1e2485_2_690x657.png)

20250223_12h27m28s_grim1353×1290 571 KB](/uploads/short-url/4SafKbmSGOa4W8nQRpUfpdEGE6x.png?dl=1)

i’m not using any of the 3d luts (maybe i should bake such things), so it’s doing the full spectral upsampling and integration. makes it kinda slow, the full raw resolution processes here in 27ms.

also i had some numerical issues with log10, i *think* i can just do natural exp/log and scale the lut accordingly.

---

## #85 **Jakob Andrén** (@jandren) · 2025-02-23 12:38

A try on how I interpreter those “negative colors” and their purpose a chart:

I see the linear RGB input values as basically 3D coordinates with no real limitation, i.e. we can be anywhere in that space. So we should test that our algorithm is robust for all possible inputs in a reasonably fast way, making sure that those stays black is one way of testing that.

What makes me excited about this spectral stuff is that we can have a better definition of the boundary of valid colors by saying that the spectra has to be positive. In contrast to f.ex. rec-709 (sRGB) primaries that is way smaller than the spectral locus and thus have valid RGB coordinates with negative values in them!

> makes it kinda slow, the full raw resolution processes here in 27ms.

[![:rofl:](https://discuss.pixls.us/images/emoji/apple/rofl.png?v=12)](https://discuss.pixls.us/images/emoji/apple/rofl.png?v=12)

 I think you can call it slow once you remove that “m” in front of the “s”.

---

## #86 **** (@mikae1) · 2025-02-23 12:53

> **@hanatos** (帖子 #84):
> thanks for all your explanations! i think i got very many details wrong, and i’m ignoring all the normalisations and illuminants involved in making the image… but i cat at least get recognisable pixels now:

Wait a min… Have you already begun porting the Python code to C? Or is this implemented [like in ART](https://discuss.pixls.us/t/spectral-film-simulations-in-art/48442/)?

> **@jandren** (帖子 #85):
> makes it kinda slow, the full raw resolution processes here in 27ms.

 I think you can call it slow once you remove that “m” in front of the “s”.

I agree, that’s blazing fast!

[![:raised_hands:](https://discuss.pixls.us/images/emoji/apple/raised_hands.png?v=12)](https://discuss.pixls.us/images/emoji/apple/raised_hands.png?v=12)

---

## #87 **jo** (@hanatos) · 2025-02-23 13:08

> **@jandren** (帖子 #85):
> once you remove that “m” in front of the “s”.

heh, i have absolutely no plans for that

[![:smiley:](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)

 i want to understand more how the results are formed and which parameters are essential, then implement the grain and preflash etc (left out quite a few things now), and then get into perf optimisation.

and yes, negative rgb is just fine. negative spectral energy is not. the sigmoidal spectral upsampling table i created a few days ago will upsample *everything*, and it will even be meaningful inside spectral locus. outside it just uses inpainting to give you a positive spectrum close to the coordinate you requested.

> **@mikae1** (帖子 #86):
> Wait a min… Have you already begun porting the Python code to C?

glsl. i don’t really speak python and i absolutely hate it if software stacks up toolchains (like shellscript stuff in latex packages…).

---

## #88 **** (@mikae1) · 2025-02-23 13:52

> **@hanatos** (帖子 #87):
> glsl.

Too cool! I hope you’re all prepared for an onslaught of grain loving YouTubers once this gets more accessible.

[![:wink:](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)

---

## #89 **** (@commutergraphics) · 2025-02-23 14:22

this seems really great, I’d been imagining ways to manipulate grain in interesting ways for a while now, it’s not very faithful to film but I’ve been thinking about things like different sizes of grains for different tonal levels doing it with a simulation seems like a possible way to experiment, then maybe do dumb stuff like arrange underlying grains in a perfect grid or different types of random patterns etc, stuff that couldn’t be done with film, maybe that would be something like masking areas in darktable then applying different instances of this to it, frankensteins film, velvia in the skies and astia for the birds

---

## #90 **Andrea** (@arctic) · 2025-02-23 17:35

> **@hanatos** (帖子 #84):
> i’m not using any of the 3d luts (maybe i should bake such things), so it’s doing the full spectral upsampling and integration. makes it kinda slow, the full raw resolution processes here in 27ms.

27 ms, thats crazy! I think that the “camera” 3D LUT and the “scanner” 3D LUT could be backed. I am not sure about the “enlarger” one, since the color balancing with CMY filters is changing the LUT, and this is one of the main controls.

The fact that you can see at the end of the pipeline is already something!

[![:grin:](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)

> **@jandren** (帖子 #85):
> I see the linear RGB input values as basically 3D coordinates with no real limitation, i.e. we can be anywhere in that space. So we should test that our algorithm is robust for all possible inputs in a reasonably fast way, making sure that those stays black is one way of testing that.

Thanks for the comment, it makes sense. Negative ACES2065-1 values are for sure outside of the visible locus, so I guess it is kind of an extreme region to test computations on visible images, but with spectral processing maybe it has more meaning.

---

## #91 **jo** (@hanatos) · 2025-02-23 18:32

… i can not for my life get neutral renditions out of this:

[[![20250223_19h29m22s_grim](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/d/cde99825b6fcee19dab4ec6f412109826df9bd15_2_690x616.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/d/cde99825b6fcee19dab4ec6f412109826df9bd15_2_690x616.png)

20250223_19h29m22s_grim1774×1584 1.74 MB](/uploads/short-url/tnAm0wMdZOKBFe1ye4sdl412s1D.png?dl=1)

this is with enlarger filters set to 0.005,0.008,1…

are there any obvious places where overall colour balance would be thrown off? oh, and this lamp, does it have a base spectrum on its own? now i’m just mixing the thorlabs filters…

i’m also not using any of the D50 or D55 illuminants… but i figured illuminant E is not *too* far off.

---

## #92 **Andrea** (@arctic) · 2025-02-23 18:33

I implemented and tested a bit the method of spectral upsampling by [@hanatos](/u/hanatos). It is available in the `large-color-space` branch of `agx-emulsion`, I will move it to the `main` after some more testing.

I have some preliminary qualitative results (using raw files from [signatureedits.com](http://signatureedits.com)). I think overall there is an effect on the saturated colors. The new method from hanatos (called here `hanatos2025`) can produce spectra for any tristimulus value in the visible locus. I think it is great for it’s simplicity and results. The old method called `mallett2019` is only valid tor sRGB, so it transforms and clips the values to sRGB before the spectral upsampling.

I exported some test raw images in linear Rec2020 and run some simulations.

Here are a few comparisons, in which I changed only the upsampling method keeping all the other parameters unchanged (unless stated).

(left) `hanatos2025` and (right) `mallett2019`, Kodak Portra 400 and Portra Endura

[[![hanatos2025_portra_portra](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/e/9e2c3ce9da10c2693c6fe6f26b22c6504dc4ddad_2_330x220.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/e/9e2c3ce9da10c2693c6fe6f26b22c6504dc4ddad_2_330x220.png)

hanatos2025_portra_portra2000×1334 3.75 MB](/uploads/short-url/mzgdCtE043aEz1zbNzCYO4hWxZz.png?dl=1)

[[![mallett2019_portra_portra](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/f/2f5b812246944df6298a4b9c1375b41f56deb501_2_330x220.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/f/2f5b812246944df6298a4b9c1375b41f56deb501_2_330x220.png)

mallett2019_portra_portra2000×1334 3.72 MB](/uploads/short-url/6KWuhAvs0hn4Hq77WkssM3k835v.png?dl=1)

As a side note, I added also a band pass filter to the virtual camera (filtering near UV below 400 nm and above 680 nm). The most problematic point was that some stocks like Portra 400 have a very blue/near UV absorption and the upsampling methods really do not limit what happens when XYZ sensitivities goes to zero.

The filter look like this:

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/6/06b69d7f293316265e727ce44256329670a16c1b.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/6/06b69d7f293316265e727ce44256329670a16c1b.png)

image560×455 38.2 KB](/uploads/short-url/Xo7cp8ZVk3vXdxlx6K3ZwwmdV9.png?dl=1)

In blue is shown the sum of the standard observer XYZ sensitivities. The band pass cuts the part of the spectra that cannot be constrained by the upsampling methods (that optimized for minimum XYZ error).

I already noticed from the beginning of the project that reds in portra were quite pink compared to other stocks. Now they behave in a more reasonable way.

(left) `hanatos2025` with filter and (right) `hanatos2025` without filter, Kodak Portra 400 and Portra Endura

[[![hanatos2025_portra_portra](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/e/9e2c3ce9da10c2693c6fe6f26b22c6504dc4ddad_2_330x220.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/e/9e2c3ce9da10c2693c6fe6f26b22c6504dc4ddad_2_330x220.png)

hanatos2025_portra_portra2000×1334 3.75 MB](/uploads/short-url/mzgdCtE043aEz1zbNzCYO4hWxZz.png?dl=1)

[[![hanatos2025_portra_portra_noUVfilter_-15Y0M](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/e/1eecbc7fa59397907d25432e1ebf0c5091e29443_2_330x220.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/e/1eecbc7fa59397907d25432e1ebf0c5091e29443_2_330x220.png)

hanatos2025_portra_portra_noUVfilter_-15Y0M2000×1334 3.78 MB](/uploads/short-url/4pzwONUjDNYgXlek6v5VcdLFMsP.png?dl=1)

I compensated the image without bandpass filter (-15Y) to balance a bit the warmth.

(left) `hanatos2025` and (right) `mallett2019`, Kodak Portra 400 and Portra Endura

[[![hanatos2025_portra](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/9/e945ab159ec1beb90ef1a7834c6f73a1382168b0_2_330x220.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/9/e945ab159ec1beb90ef1a7834c6f73a1382168b0_2_330x220.png)

hanatos2025_portra2000×1335 3.93 MB](/uploads/short-url/xhCvSNCH115AII9KBvYP6d9luc8.png?dl=1)

[[![mallett2019_portra](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/f/8f239cb3dc22f3e3d147cdf0ad6334c72ba9c284_2_330x220.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/f/8f239cb3dc22f3e3d147cdf0ad6334c72ba9c284_2_330x220.png)

mallett2019_portra2000×1335 3.96 MB](/uploads/short-url/kqgzLyCrV99v8aLvVQdgaMNc9tG.png?dl=1)

[[![hanatos2025_portra_crop](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/b/cbfdd2179d5289774411f51b01d5ac45ad5f7b6f.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/b/cbfdd2179d5289774411f51b01d5ac45ad5f7b6f.png)

hanatos2025_portra_crop560×560 420 KB](/uploads/short-url/t6AJyvLhBzd26rzu6Sbqa8vyIP5.png?dl=1)

[[![mallett2019_portra_crop](https://d2x313g9lpht1q.cloudfront.net/original/3X/2/7/275b85d0eb737316903f9e9f25ceef5d4f5dc1a6.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/2/7/275b85d0eb737316903f9e9f25ceef5d4f5dc1a6.png)

mallett2019_portra_crop560×560 432 KB](/uploads/short-url/5CaHT2Yg0m119byO6yJ5ADFijnE.png?dl=1)

The crop of the background shows that `hanatos2025` is more smooth in the high saturation yellow flowers, retaining the smooth color transition to the center of the flowers.

(left) `hanatos2025` and (right) `mallett2019`, Kodak Gold 200 and Portra Endura

[[![hanatos2025_gold_portra](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/9/09dd326e0ae7cec93a4d159eb9d91b2a0e1d1630_2_330x480.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/9/09dd326e0ae7cec93a4d159eb9d91b2a0e1d1630_2_330x480.png)

hanatos2025_gold_portra1334×2000 3.8 MB](/uploads/short-url/1pgcZIfaNwwpmRWl1JOQUvdehig.png?dl=1)

[[![mallett2019_gold_portra](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/f/eff4afb3285ae56adbfa24d20187d0bc8eff98a2_2_330x480.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/f/eff4afb3285ae56adbfa24d20187d0bc8eff98a2_2_330x480.png)

mallett2019_gold_portra1334×2000 3.84 MB](/uploads/short-url/yeKlULgTTL9FixxRmPcFxE5whSW.png?dl=1)

In this portrait, `hanatos2025` retains some more saturation, and I think the transition with the out of focus edge of the hair is more pleasing. The image seams also to have more “depth”.

(left) `hanatos2025` and (right) `mallett2019`, Kodak Gold 200 and Portra Endura

[[![hanatos2025_gold_portra](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/a/2aea684b8e1f283095ff1dc903dc27fc1bb910e9_2_330x220.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/a/2aea684b8e1f283095ff1dc903dc27fc1bb910e9_2_330x220.png)

hanatos2025_gold_portra2000×1335 4.36 MB](/uploads/short-url/67EgHcwBINqsey2lEJnjBi9DwDv.png?dl=1)

[[![mallett2019_gold_portra](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/1/31113d6e3573cdc279f29015291706ce01d0a623_2_330x220.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/1/31113d6e3573cdc279f29015291706ce01d0a623_2_330x220.png)

mallett2019_gold_portra2000×1335 4.34 MB](/uploads/short-url/704kC8zQ6p3BM3yZ48rRxCBaImv.png?dl=1)

Some special colors are definitely more affected than others, like lime-greens.

I did also some quick test with this stress test image that explore the edges of a color space and the desaturation paths. This stress test image already presented earlier in the thread.

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/d/3/d33774e3718fe35c9b6ee523d8d176bf1b30f6c2.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/d/3/d33774e3718fe35c9b6ee523d8d176bf1b30f6c2.png)

image630×628 69.3 KB](/uploads/short-url/u8vyOiEOgBgI2joU7k4FYQVeud4.png?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/1/4/146687c64a75cf4b4b8491a2916f149179ba861f.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/1/4/146687c64a75cf4b4b8491a2916f149179ba861f.jpeg)

image389×389 20.3 KB](/uploads/short-url/2UtdCzBQmPKk3HMUyEvBcgGJ1CL.jpeg?dl=1)

This is when I imported the image as sRGB with cctf decoding active.

(left) `hanatos2025` and (right) `mallett2019`, Kodak Portra 400 and Portra Endura

[[![hanatos2025_srgb_cctf_1pe_0stops](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/5/a59d110edd572634e1810f6d7055b2536474bd1f_2_330x165.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/5/a59d110edd572634e1810f6d7055b2536474bd1f_2_330x165.png)

hanatos2025_srgb_cctf_1pe_0stops1000×500 543 KB](/uploads/short-url/nD5in6yFuBsiPFGkzr2twCtVGYD.png?dl=1)

[[![mallett2019_srgb_cctf_1pe_0stops](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/b/5bbbb129d8e303ba8b2d4018f620ed5c85016a52_2_330x165.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/b/5bbbb129d8e303ba8b2d4018f620ed5c85016a52_2_330x165.png)

mallett2019_srgb_cctf_1pe_0stops1000×500 542 KB](/uploads/short-url/d5vzQsfj8cNNrDnzRiwCk8lHchc.png?dl=1)

By bumping exposure 2 stops and 0.25 print exposure we can reveal the “cyan catastrophy”, also noticed by [@liam_collod](/u/liam_collod) in his tests. The new method seams a bit worse at it.

(left) `hanatos2025` and (right) `mallett2019`, Kodak Portra 400 and Portra Endura

[[![hanatos2025_srgb_cctf_025pe_2stops](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/0/e067f943026718f3c5801b98060396d327f060b5_2_330x165.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/0/e067f943026718f3c5801b98060396d327f060b5_2_330x165.png)

hanatos2025_srgb_cctf_025pe_2stops1000×500 337 KB](/uploads/short-url/w1bIo9i40qFBHlAR2nR3TGCPcQB.png?dl=1)

[[![mallett2019_srgb_cctf_025pe_2stops](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/c/2c34f298bf1a587ec16e8eb4a70eac831c94f3ff_2_330x165.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/c/2c34f298bf1a587ec16e8eb4a70eac831c94f3ff_2_330x165.png)

mallett2019_srgb_cctf_025pe_2stops1000×500 342 KB](/uploads/short-url/6j4rO2D5KrQhAtWrKw0YUeYnlGT.png?dl=1)

We can also import the image as if it was linear Rec2020, and explore the edge of the Rec2020 color space.

(left) `hanatos2025` and (right) `mallett2019`, Kodak Portra 400 and Portra Endura

[[![hanatos2025_rec2020_linear_1pe_0stops](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/c/bc80d1968b0f038386c012b647d71809eb4a83b6_2_330x165.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/c/bc80d1968b0f038386c012b647d71809eb4a83b6_2_330x165.png)

hanatos2025_rec2020_linear_1pe_0stops1000×500 540 KB](/uploads/short-url/qTzKWQkndQ7PACA4raCLjW6DYYm.png?dl=1)

[[![mallett2019_rec2020_linear_1pe_0stops](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/5/65c52ba75501c73ff0d5dff9d47f1644e787d928_2_330x165.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/5/65c52ba75501c73ff0d5dff9d47f1644e787d928_2_330x165.png)

mallett2019_rec2020_linear_1pe_0stops1000×500 556 KB](/uploads/short-url/ewiEWCkkBE96LbDtnLg22oawcbK.png?dl=1)

0 stops, 1.0 print esposure

[[![hanatos2025_rec2020_linear_025pe_2stops](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/4/24b0897098952591ba2e55668b99efe71d23025b_2_330x165.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/4/24b0897098952591ba2e55668b99efe71d23025b_2_330x165.png)

hanatos2025_rec2020_linear_025pe_2stops1000×500 355 KB](/uploads/short-url/5ezpSEQeWMRumrQgN53cIh8lJNh.png?dl=1)

[[![mallett2019_rec2020_linear_025pe_2stops](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/d/6de5cc84c0fcedc90c525ee88257be6dec1ca595_2_330x165.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/d/6de5cc84c0fcedc90c525ee88257be6dec1ca595_2_330x165.png)

mallett2019_rec2020_linear_025pe_2stops1000×500 359 KB](/uploads/short-url/fGcnWn3TUrECvyfercV0VmCiKHz.png?dl=1)

+2 stops, 0.25 print exposure

There are some issue with the very blue corner of Rec2020 with `hanatos2025`, and the sRGB clipping of `mallett2019` is super clear. The performance on the large color space are clearly much better for `hanatos2025` with no surprises here.

---

## #93 **Andrea** (@arctic) · 2025-02-23 18:45

> **@hanatos** (帖子 #91):
> … i can not for my life get neutral renditions out of this:

This has been a huge struggle also for me, for quite a long time. I have seen all the possible weird colors.

Color enlargers uses tungsten bulbs (approx. 3200K), and sensitivities of print paper are balanced for it, i.e. they have stronger blue sensitivity compared to red. In the simulation I am using a black body emission spectrum at 3200K.

This is Kodak Portra Endura sensitivities as an example.

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/a/6/a6ba9b6fbf83b15f08191b275dc652e34cd3e7e1.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/a/6/a6ba9b6fbf83b15f08191b275dc652e34cd3e7e1.png)

image474×403 33.4 KB](/uploads/short-url/nMX3YtLpu8fdfWGPE8Y2vIrHHeV.png?dl=1)

Right now I am always keeping fixed the cyan filter at 0.35 (in a 0-1 range), and on average the yellow filter is 0.6-0.8 and the magenta filter 0.4-0.6. The value used in the python package are in the `.json` of fitted neutral filters in `agx_emulsion/data/profiles`.

Also in the real darkroom workflow, the C filter should not be touched and only Y and M filters should be used.

> **@hanatos** (帖子 #91):
> i’m also not using any of the D50 or D55 illuminants… but i figured illuminant E is not too far off.

This is probably true, I just used them as the one recommended for viewing the prints (D50, used to compute the final XYZ >> RGB for viewing the print) and for the neutral density measurements by kodak (D55). But not used in the sim otherwise (or better `mallett2019` used them).

---

## #94 **jo** (@hanatos) · 2025-02-23 18:52

> **@arctic** (帖子 #92):
> There are some issue with the very blue corner of Rec2020 with hanatos2025,

hm could this be the case where the spectral peak is way narrower than the 5nm spacing used for integration? that might explain the sharp drop in brightness for some shape of blue. i suppose since we know where the peak is we could devise specialised quadrature rules/monte carlo importance sampling.

---

## #95 **Andrea** (@arctic) · 2025-02-23 19:05

I ended up computing the spectra with a 1 nm resolution (should be enough right?), blurring them with 2.5 nm sigma gaussian kernel (approx 6 nm FWHM), and resampling them at 5 nm step. Still the issue might be present. I can try to blur them more and see if the drop in brightness improves.

Edit:

This is with spectra computed with 0.5 nm step and blurred with a 10 nm sigma, then resampled at 5 nm step.

[[![hanatos2025_rec2020_linear_025pe_2stops_05nm_compu_10nmsigma_blur](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/6/360003eff2d464f12b1f0c38ba2644a893dd6953_2_690x345.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/6/360003eff2d464f12b1f0c38ba2644a893dd6953_2_690x345.png)

hanatos2025_rec2020_linear_025pe_2stops_05nm_compu_10nmsigma_blur1000×500 333 KB](/uploads/short-url/7HHOC4tagJSV9RuciwxgeBhdRF9.png?dl=1)

---

## #96 **jo** (@hanatos) · 2025-02-24 07:55

hmm okay thanks. so you’re saying it just looks like that. these gradient images are generated how? probably some hsv bs and then converted to rgb and that simply reinterpreted as rec2020… nobody says this is smooth to begin with.

---

## #97 **Andrea** (@arctic) · 2025-02-24 08:52

> **@hanatos** (帖子 #96):
> these gradient images are generated how? probably some hsv bs and then converted to rgb

Even worse, just some arbitrary ramps over the edge of the color space. The bottom part of the “stress test image” is made by scaling the RGB plot below from 0 to 1.

Indeed I don’t like it much. I have just seen them around (in not scientific settings) when comparing film sim. So I agree that this is a bit of a dumb qualitative comparison.

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/0/50fb35a9749c6b61e90e4929e7039f82d696b18c.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/0/50fb35a9749c6b61e90e4929e7039f82d696b18c.png)

image547×420 32.7 KB](/uploads/short-url/byopwNsrMSXBdmhstKXDaZl4ona.png?dl=1)

CIECAM16 lightness looks pretty spiky, so the discontinuity should be expected. I got to find better ways.

Also the interplay of the spectra with sensitivities and the later part of the film sim pipe might not be straightforward.

---

## #98 **jo** (@hanatos) · 2025-02-24 12:15

some more detailed questions:

- density_cmy is 3 channels per pixel and holds c,m,y as the name suggests, and in this order? because the order on the lamp filters is ymc.
- how do i get density_cmy? by doing a per-channel lookup of log_raw (rgb) through the density_curves lut? like log_raw.r → density_curves.r → density_cmy.r?
- how do i get spectral density from density_cmy and the dye densities? dye_density is three spectral quantities, so i multiply density_cmy.r to dye_density.r[wavelength], do that for r,g,b and sum the three spectra? (and then add the min density/fourth channel times some constant regardless of density_cmy)
- the filters are transmittance filters, right? so i blend in the “strength” of the filter by mixing it with a constant 1.0 spectrum, and then multiply all three spectral filters (for c,m,y).

---

## #99 **Bob** (@PhotoPhysicsGuy) · 2025-02-24 12:58

> **@hanatos** (帖子 #96):
> nobody says this is smooth to begin with.

It’s the outer surface of whatever RGB cube you have. Cube corners and edges aren’t smooth (trivial), but the cube-faces are as smooth as can be.

That cyan behaves different than yellow is the oddity, imho.

(In testing LUTs or DRTs the cube-faces should at least stay smooth and don’t get more kinks. In addition the gamut edges and corners could be translated into smooth edges/corners as well. Channel crosstalk would smooth out edges for example. It’s a stress test because it samples the input-RGB basis-vectors and their mixtures. If the output of that is smooth, things closer to the [0,0,0] to [1,1,1] axis probably behave as well, except for really broken LUTs. )

---

## #100 **Andrea** (@arctic) · 2025-02-24 14:57

> **@hanatos** (帖子 #98):
> density_cmy is 3 channels per pixel and holds c,m,y as the name suggests, and in this order? because the order on the lamp filters is ymc.

The order CMY (analogously to RGB) is correct for the variable `density_cmy` and used everywhere except enlarger filters. The choice of having the fitted neutral filters as YMC came from studying physical enlargers datasheet, I read some stuff from Durst for example.

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/9/8/986093b3fabcf138539a7b18d63f46c6a4249446.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/9/8/986093b3fabcf138539a7b18d63f46c6a4249446.jpeg)

image597×523 31.9 KB](/uploads/short-url/lJZuqfUC3majZCCY8AIgi21JSey.jpeg?dl=1)

In the physical devices from Durst and their manuals, the order of the filters is usually YMC. Y roughly controls temperature and M tint. It is probably an unhappy choice for the code.

> **@hanatos** (帖子 #98):
> how do i get density_cmy? by doing a per-channel lookup of log_raw (rgb) through the density_curves lut? like log_raw.r → density_curves.r → density_cmy.r?

Yes!

I compute `raw` as the product of the irradiance spectra and the sensitivities, then integrate over the wavelengths.

<pre data-code-wrap="python"><code class="lang-python">raw = contract('ijk,km->ijm', spectra, sensitivity)
</code></pre>

I make sure that `raw` is normalized such that whatever i think should be midgray in the image has value 1 (normalizing only by the green channel). And apply exposure.

<pre data-code-wrap="python"><code class="lang-python">illuminant = spectra_lut[-1,-1,-1] # spectrum for input linear RGB=[1,1,1]
raw_midgray = np.einsum('k,km->m', illuminant*0.184, sensitivity) # use 0.184 as midgray reference
raw /= raw_midgray[1]

raw *= 2**exposure_ev
</code></pre>

Then I do a linear interpolation of `density_curves` (again RGB/CMY ordering), that is represented on the x axis variable `log_exposure`, both in the json, with the `log_raw` data computed (`log10(raw)`).

> **@hanatos** (帖子 #98):
> how do i get spectral density from density_cmy and the dye densities? dye_density is three spectral quantities, so i multiply density_cmy.r to dye_density.r[wavelength], do that for r,g,b and sum the three spectra? (and then add the min density/fourth channel times some constant regardless of density_cmy)

That sounds correct!

`density_cmy` multiplies `dye_density` spectra channel wise. And the fourth column `dye_density[:,3]` is the density minimum, and it is summed.

<pre data-code-wrap="python"><code class="lang-python">def compute_density_spectral(profile, density_cmy):
 density_spectral = contract('ijk, lk->ijl', density_cmy, profile.data.dye_density[:, 0:3])
 density_spectral += profile.data.dye_density[:, 3] * profile.data.tune.dye_density_min_factor
 return density_spectral
</code></pre>

In this snippet: `ij` are the pixel of the image, `k` is the CMY channel, `l` is the wavelegth.

> **@hanatos** (帖子 #98):
> the filters are transmittance filters, right? so i blend in the “strength” of the filter by mixing it with a constant 1.0 spectrum, and then multiply all three spectral filters (for c,m,y).

Filters are in transmittance, and taken from Thorlabs datasheets (only the CMY ones):

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/f/f/ff4296d49ca52ccfa45f220f183f0c223997fb37.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/f/f/ff4296d49ca52ccfa45f220f183f0c223997fb37.png)

image918×567 33.8 KB](/uploads/short-url/Aq8q8JPRlC4ToEmqvRlzTV3UhTh.png?dl=1)

In my code I blend the filters and apply them to a 3200K black body illuminant with this code:

```
dimmed_filters = 1 - (1-filters)*ymc_filter_values # following durst 605 wheels values, with 170 max
total_filter = np.prod(dimmed_filters, axis=1)
filtered_illuminant = illuminant*total_filter

```

here `filters` is an array [wavelenghts, ymc_channels], and `ymc_filter_values` a 1D array with the three filter values in a 0-1 range.

---

## #101 **Andrea** (@arctic) · 2025-02-24 15:00

> **@PhotoPhysicsGuy** (帖子 #99):
> It’s the outer surface of whatever RGB cube you have. Cube corners and edges aren’t smooth (trivial), but the cube-faces are as smooth as can be.
That cyan behaves different than yellow is the oddity, imho.

That makes sense.

I am investigating a bit on the cyan misbehavior, that is really only clear when overexposing the film. So probably some crosstalk among the channel should be preserved/manually introduced to guarantee desaturation. It might be very well connected with some aspect of the film/paper profiles creations.

---

## #102 **jo** (@hanatos) · 2025-02-24 15:17

awesome. i think for the most part i do exactly that. i suppose something with a bit of alignment of the curves/x positions… and practice with the m y filters. but i do like the results already:

[[![20250224_15h26m49s_grim](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/b/2be98001c1933e663df73e1424580a04782694ba_2_690x626.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/b/2be98001c1933e663df73e1424580a04782694ba_2_690x626.png)

20250224_15h26m49s_grim1521×1380 1.75 MB](/uploads/short-url/6gsNLGUICDL3nUY5p92EuI7QYci.png?dl=1)

now i want to do at least *some* grain before cleaning up and pushing…

---

## #103 **Andrea** (@arctic) · 2025-02-24 15:38

That was fast!

[![:star_struck:](https://discuss.pixls.us/images/emoji/apple/star_struck.png?v=12)](https://discuss.pixls.us/images/emoji/apple/star_struck.png?v=12)

It is getting closer

[![:+1:](https://discuss.pixls.us/images/emoji/apple/+1.png?v=12)](https://discuss.pixls.us/images/emoji/apple/+1.png?v=12)

 Great job!

If you need any in input on the grain I can help.

I use poisson and binomial random numbers in simulating grain. And apply gaussian blurs according to particle sizes (or better amount of density per particle). I guess there are crazy fast random number generators for GPUs.

---

## #104 **jo** (@hanatos) · 2025-02-24 15:46

> **@arctic** (帖子 #103):
> If you need any in input on the grain I can help.

yes please.

[![:smiley:](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)

 that data. the 3x3 per density. what is it? it’s like 1e-80 or something that is clearly not 32-bit floating point any more. also, it’s resampled following data locations given by density_curves if i read that right. can i just resample it to a uniform distribution of densities? so i can do it all the same for all the profiles, and store in the same texture.

edit: maybe i was not looking at the full array… for higher densities the numbers become way more normal…

---

## #105 **Andrea** (@arctic) · 2025-02-24 16:59

> **@hanatos** (帖子 #104):
> that data. the 3x3 per density. what is it? it’s like 1e-80 or something that is clearly not 32-bit floating point any more. also, it’s resampled following data locations given by density_curves if i read that right.

In the json there is `density_curve_layers`. That array is again represented on the same `log_exposure` axis [log_exposure, sub_layers, main_layer]. The sublayers are ordered from the most sensitive and large particles to the least sensitive and smaller.

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/a/a/aa2d10a824e367d1e3da8250f336f5f509e0eb55.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/a/a/aa2d10a824e367d1e3da8250f336f5f509e0eb55.png)

image567×432 44.6 KB](/uploads/short-url/ohrIJbYZCWmWLGkWD74IzJ6BRWt.png?dl=1)

This above is an example in which RGB total is `density_curves` while the remaining nine curves are `density_curves_layers`. The sum of `density_curves_layers` along the sub_layers axis gives `density_curves`. We can have also a functional version of them, based on gaussian CDFs.

The weird thing of interpolating with density instead of log_exposure came as a consequence of the DIR couplers model. When applying DIR couplers, we need to do some trickery, and the relationship `log_raw`-`density_cmy` is not anymore simply given by `density_curves`. To solve that, since `density_curves` is anyway monotonic I used it to interpolate the given density of a sublayer (`density_cmy_layers`) given the final total density of the layer (`density_cmy`) after couplers. The other way is to output an effective `log_raw_after_dir_couplers` and use that for the interpolation.

---

## #106 **Jakob Andrén** (@jandren) · 2025-02-24 18:25

Haha you two are crazy fast!

On the topic of testing the spectral upsampling, the engineer in me had liked proof of robust and smooth results for any RGB input. The RGB gamut boundary is one way of generating that. Here is another possibility I generated with some python hacking.

[[![Constant sum test clipped preview](https://d2x313g9lpht1q.cloudfront.net/original/3X/6/8/6849a506d28a69b843f46f3995ac26fa5f8ca788.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/6/8/6849a506d28a69b843f46f3995ac26fa5f8ca788.png)

Constant sum test clipped preview1111×1127 33.8 KB](/uploads/short-url/eSzrgHRE6itZSqE4AJFN48lIMhW.png?dl=1)

[constant_sum.exr](/uploads/short-url/iAED154mxIU4alW6i6WHxrCD6SF.exr) (3.7 MB)

And the script if you want to modify anything.

[generate_constant_sum_slice.py](/uploads/short-url/kMGvxq7emYczD196CjHZnr66gSj.py) (948 Bytes)

It provides a slice of the RGB volume of constant sum, so a plane with the normal [1, 1, 1] with plenty of “negative colors” around the valid triangle. Making sure that this test plane works fine for both low, mid and high exposure (i.e. “all”) and it should be a pretty good proof of the spectral upsampling working well. This is what I was planning on testing with but I won’t be able to provide results in adequate time for your tempo so I hope a proposed test image will help enough.

My expectation is that all colors, even monochromatic lasers, at some point go to white.

---

## #107 **** (@mikae1) · 2025-02-24 20:06

> **@hanatos** (帖子 #102):
> i do like the results already

[![:star_struck:](https://discuss.pixls.us/images/emoji/apple/star_struck.png?v=12)](https://discuss.pixls.us/images/emoji/apple/star_struck.png?v=12)

> **@hanatos** (帖子 #102):
> now i want to do at least some grain before cleaning up and pushing…

Implementing grain is interesting from a pipeline perspective. Adding grain *post* interpolation is one of the best ways of hiding interpolation artifacts. My 21 MP 5D Mark II files looked amazing at almost 100 cm on the longest side if images were run through Alien Skin Exposure’s color film simulation post interpolation. I used this a lot when doing exhibition printing for work. This has always meant I can’t do everything in darktable or Lightroom.

Upsizing images with grain already applied, on the other hand, looks rather terrible.

It was a long time since I tried vkdt (looks like that will change soon!), is it possible put modules/effects post interpolation/upsizing?

---

## #108 **jo** (@hanatos) · 2025-02-24 20:43

> **@mikae1** (帖子 #107):
> is it possible put modules/effects post interpolation/upsizing?

hm i have explicit resize nodes that instruct the graph where you want resolution to change if both ends don’t agree. with the film sim i’ll probably make it an explicit upsampling thing that would interpolate / catmul rom the input image and then simulate grain on the output size.

can’t tell you how much i’m enjoying *generating* noise. normally i spend my days trying to *reduce* noise in estimators…

[[![20250224_21h43m05s_grim](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/0/7035b639b90f322bf9eb84ee90c8334e0ad46c59_2_659x1000.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/0/7035b639b90f322bf9eb84ee90c8334e0ad46c59_2_659x1000.png)

20250224_21h43m05s_grim907×1375 2.14 MB](/uploads/short-url/g0EykxpXKbxk6HkEAPoyakiAFvP.png?dl=1)

---

## #109 **** (@mikae1) · 2025-02-24 21:00

> **@hanatos** (帖子 #108):
> with the film sim i’ll probably make it an explicit upsampling thing that would interpolate / catmul rom the input image and then simulate grain on the output size.

If I get that right, that means grain is applied after the upsampling? That would be just… Amazing!

> **@hanatos** (帖子 #108):
> can’t tell you how much i’m enjoying generating noise. normally i spend my days trying to reduce noise in estimators…

Not all noise/grain is equal! Enjoy your upsampling masquerading.

[![:smiley:](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)

---

## #110 **Andrea** (@arctic) · 2025-02-25 00:41

> **@jandren** (帖子 #106):
> Haha you two are crazy fast!

I had some spare time recently (that’s not always the case, though), and I got a bit over-excited for the spectral upsampling method by [@hanatos](/u/hanatos).

[![:grin:](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)

 In my opinion It definitely improves the results in practical tests. I like images much more, at least.

> **@jandren** (帖子 #106):
> And the script if you want to modify anything.
generate_constant_sum_slice.py (948 Bytes)

Thanks for sharing!

[![:smiley:](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)

> **@jandren** (帖子 #106):
> My expectation is that all colors, even monochromatic lasers, at some point go to white.

I am not an expert but that sounds like a reasonable expectation.

For the simulation of film that I am doing, I have the fear that if the sensitivity of a channel is exactly zero at the wavelength of the monochromatic laser (this is the case for the data as they are now), there will be no density generated in that layer. Making it more difficult to reach white in the final print. Also if the dye generated in a layer with development (let’s say the one that has non zero sensitivity to the laser) does not have residual absorption in all regions of the spectrum, reaching white might be even more difficult. These also because there are maximum densities that can be created.

This is good input. I could try to make the sensitivities decay smoothly such that that they are never exactly zero. This shouldn’t change much the final images in normal conditions, but would improves desaturation behaviors with over-exposure.

> **@jandren** (帖子 #106):
> This is what I was planning on testing with but I won’t be able to provide results in adequate time for your tempo so I hope a proposed test image will help enough.

How should I treat the negative colors here? Maybe a limitation by my implementation: if I import the image in linear Rec2020 for example, I cannot ask to generate spectra outside this. The alg by hanatos actually could work on the full visible locus, but for sake of optimization I pre baked a Rec2020 LUT.

Should I import for example in linear Rec709? Is this what you envisioned?

For now I computed a couple of default simulations (Kodak Gold and Portra Endura), importing in linear sRGB (Rec 709). Probably we should isolate the spectral upsampling part to study better this aspect, also the interaction with the film sim is very interesting in my opinion. Plus, they looked colorful and fun enough to be shared.

They might show some glaring mistakes in my code. For sure before the spectral upsampling I convert in linear Rec2020 and clip negative values, leaving the upper unbounded. This to be able to use my LUT of spectra.

(left) hanatos2025, (right) mallett2019

[[![hanatos2025_linear_srgb](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/d/ad7a440424f0c1fe294969437ef61f850a0a0f46_2_330x330.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/d/ad7a440424f0c1fe294969437ef61f850a0a0f46_2_330x330.png)

hanatos2025_linear_srgb1024×1024 904 KB](/uploads/short-url/oKEyr1kAx5kr54h08zTVu8Nn7MO.png?dl=1)

[[![mallett2019_linear_srgb](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/5/f57ba01555795b24dcd5263cf3fb7bbe00bc07b6_2_330x330.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/5/f57ba01555795b24dcd5263cf3fb7bbe00bc07b6_2_330x330.png)

mallett2019_linear_srgb1024×1024 1.22 MB](/uploads/short-url/z1DQtaBJSkWAZg5cZF9zqVAR8cS.png?dl=1)

---

## #111 **Andrea** (@arctic) · 2025-02-25 00:45

That’s some grain!!!

[![:sunglasses:](https://discuss.pixls.us/images/emoji/apple/sunglasses.png?v=12)](https://discuss.pixls.us/images/emoji/apple/sunglasses.png?v=12)

Can’t say that it is enjoyable to look at in this image

[![:smile:](https://discuss.pixls.us/images/emoji/apple/smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smile.png?v=12)

, but it a good start! I am amazed by your speed, and the speed of vkdt of course.

---

## #112 **jo** (@hanatos) · 2025-02-25 07:39

> **@arctic** (帖子 #111):
> That’s some grain!!!

hehe yeah it’s completely nonsensical, pretty much just `binom(poisson(something made up of thin air that looks almost like the density))`. certainly not an indication of what it is going to look like/looks in your code.

---

## #113 **jo** (@hanatos) · 2025-02-25 15:31

not sure this test image is super relevant. i mean these coordinates are waaaaay outside:

[[![20250225_16h21m28s_grim](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/6/86b83a438a49b1c599b6378d6df36ddc97aaf5d6_2_690x426.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/6/86b83a438a49b1c599b6378d6df36ddc97aaf5d6_2_690x426.png)

20250225_16h21m28s_grim1981×1224 366 KB](/uploads/short-url/jdMGAcIRIsiBrnMih4noLucwdN4.png?dl=1)

any even partially meaningful input device transform would take care that these values are a slight bit more real. these aren’t even close to spectral locus. here i marked all the values (interpreting input as rec709/linear) that are within the super large rec2020 gamut (it touches the boundaries of the spectral locus):

[[![20250225_16h23m56s_grim](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/2/f227f2b1b226d0fbcb947c989de4740a6bad744f_2_690x436.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/2/f227f2b1b226d0fbcb947c989de4740a6bad744f_2_690x436.png)

20250225_16h23m56s_grim1914×1212 195 KB](/uploads/short-url/yyd8r9ioUGpUxyLK8xiLnVWwa1F.png?dl=1)

edit: this is spectral locus:

[[![20250225_16h35m04s_grim](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/f/dfdba257f4445baea8b13e5dc7e1adc6964b7757_2_690x515.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/f/dfdba257f4445baea8b13e5dc7e1adc6964b7757_2_690x515.png)

20250225_16h35m04s_grim1582×1183 117 KB](/uploads/short-url/vWl2tr7DXXHFW3Yb4oMsQNEpVVd.png?dl=1)

so if anything it will test the out-of-gamut inpainting of the upsampling map.

---

## #114 **Andrea** (@arctic) · 2025-02-25 22:49

> **@hanatos** (帖子 #113):
> 20250225_16h21m28s_grim1981×1224 366 KB
20250225_16h21m28s_grim1981×1224 366 KB

Plotting the xy chromaticity is very telling of the extreme range of the image. Thanks for the analysis!

After these comments, I had some fun and I also attempted to make another scene referred test image, more oriented at verifying the smoothness of the full simulation; still trying to be in a large enough gamut to be meaningful and telling of the capabilities of the spectral upsampling. Also I wanted it to be HDR.

My attempt looks something like this:

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/a/f/af71edfdbf0d7ffd1a660cd02da1d06590b4fe53.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/a/f/af71edfdbf0d7ffd1a660cd02da1d06590b4fe53.png)

image554×296 21.9 KB](/uploads/short-url/p23EksHrRLD6tqhDQQp0NexsERJ.png?dl=1)

[gradient_hdr_rgb.exr](/uploads/short-url/poUxhtqgMeUXuLowQ7ok1Gp1ex.exr) (390.8 KB)

<details>
<summary>
Code</summary>

<pre data-code-wrap="python"><code class="lang-python">from agx_emulsion.utils.io import save_image_oiio
import numpy as np
import scipy.ndimage
import matplotlib.pyplot as plt

N = 64
x=np.linspace(0, 1, 2*N)
y=np.logspace(12, -6, 4*N, base=2) * 0.184
z = np.zeros_like(x)
grad_rg = np.stack((x,1-x,z), axis=-1)
grad_gb = np.stack((z,x,1-x), axis=-1)
grad_br = np.stack((1-x,z,x), axis=-1)
grad = np.concatenate((grad_br,grad_gb,grad_rg, grad_br,grad_gb,grad_rg), axis=0)
grad = scipy.ndimage.gaussian_filter(grad, (2*N/4,0), mode='wrap')
grad = grad[:8*N,:]
grad /= np.sum(grad,axis= -1)[:,None]
grad = grad[np.newaxis,:,:] * y[:,np.newaxis,np.newaxis]
grad = np.fliplr(grad)
save_image_oiio('gradient_rgb.exr', grad, bit_depth=32)
plt.imshow(grad)
</code></pre>

</details>

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/b/5/b5611747375800ce105d2dcbe021c97a2c796a8c.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/b/5/b5611747375800ce105d2dcbe021c97a2c796a8c.png)

image547×403 29.8 KB](/uploads/short-url/pSyrbDif9CWvhWwPhH7hrADh8YY.png?dl=1)

The image is made by scaling these RGB profiles with a log-spaced amplitude. The sum of RGB is 1 for the base profile, and the intensity spans from -6 to +10 stops of 0.184 midgray (i.e. [0.184,0.184,0.184] * scaling factor).

If interpreted as Rec2020 it covers this profile in the xy chromaticity space:

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/9/a/9a7e3fd3e24fde1771f9479e5283c387e9987b45.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/9/a/9a7e3fd3e24fde1771f9479e5283c387e9987b45.png)

image630×605 54.2 KB](/uploads/short-url/m2I18FwEY9YVzpEd86tfRk7LS0R.png?dl=1)

It is not going to the edges, but it tries to be smooth.

With a default simulation (deactivating auto-exposure) we get:

Kodak Gold 200 and Kodak Portra Endura, (left) hanatos2025 (right) mallett2019

[[![gradient_hdr_rgb_gold_portra](https://d2x313g9lpht1q.cloudfront.net/original/3X/a/0/a0f8e19ac05c3465f0a055fdbedb5f0632272ea0.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/a/0/a0f8e19ac05c3465f0a055fdbedb5f0632272ea0.png)

gradient_hdr_rgb_gold_portra448×256 56 KB](/uploads/short-url/mY1CuQCK19Q2dBpmhfECb3vGayY.png?dl=1)

[[![gradient_hdr_rgb_gold_portra_mallett2019](https://d2x313g9lpht1q.cloudfront.net/original/3X/b/3/b3cb9eba2a9c2a5130915cf2fdae4b946781e398.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/b/3/b3cb9eba2a9c2a5130915cf2fdae4b946781e398.png)

gradient_hdr_rgb_gold_portra_mallett2019448×256 53.9 KB](/uploads/short-url/pExIHWpndgjRUSEiZCenJsZm9S0.png?dl=1)

And with Kodak Portra 400 and Kodak Portra Endura, (left) hanatos2025 (right) mallett2019

[[![gradient_hdr_rgb_portra_portra](https://d2x313g9lpht1q.cloudfront.net/original/3X/a/c/acf45cfb37256b46058ba5a8c4dfd82181b40676.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/a/c/acf45cfb37256b46058ba5a8c4dfd82181b40676.png)

gradient_hdr_rgb_portra_portra448×256 55 KB](/uploads/short-url/oG1FA4WO8UV7g0ZcgZ0R52EqWKW.png?dl=1)

[[![gradient_hdr_rgb_portra_portra_mallett2019](https://d2x313g9lpht1q.cloudfront.net/original/3X/1/d/1d141ff0564a686290e400e0c4b918b93a0c51ff.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/1/d/1d141ff0564a686290e400e0c4b918b93a0c51ff.png)

gradient_hdr_rgb_portra_portra_mallett2019448×256 53.8 KB](/uploads/short-url/49eXKDkhbptjAUlLMRVPUIYNs9F.png?dl=1)

I had a closer look at the cyan region for some insight on the “cyan discontinuity”. If we take a vertical section at around 2/3 the x axis we get this:

(left) sRGB output, (right) Linear Rec2020 output

[[![gradient_hdr_rgb_gold_portra_section310_srgb](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/d/0d3dd46ec7ef5d34131a0be8b6cd0c5da1f4aff9.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/d/0d3dd46ec7ef5d34131a0be8b6cd0c5da1f4aff9.png)

gradient_hdr_rgb_gold_portra_section310_srgb547×420 22.9 KB](/uploads/short-url/1T8FXWuDMcc81ieCwdee9htUUop.png?dl=1)

[[![gradient_hdr_rgb_gold_portra_section310_linear_rec2020](https://d2x313g9lpht1q.cloudfront.net/original/3X/e/f/eff8670205ef0f564955c0f6bda3c9c8bcbd5f53.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/e/f/eff8670205ef0f564955c0f6bda3c9c8bcbd5f53.png)

gradient_hdr_rgb_gold_portra_section310_linear_rec2020547×420 23 KB](/uploads/short-url/yeSjx879awNe9Bb0tcK4Gmi6aXN.png?dl=1)

sRGB is clearly clipping creating the hard edge in the cyan.

Outputing in Rec2020 (and then reinterpreting here on the browser in sRGB) shows a smooth cyan transition (with Kodak Gold 200 and Portra Endura).

[[![gradient_hdr_rgb_gold_portra_rec2020](https://d2x313g9lpht1q.cloudfront.net/original/3X/d/8/d86a9e862f0423c042ead2aaa2341efb9563fba1.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/d/8/d86a9e862f0423c042ead2aaa2341efb9563fba1.png)

gradient_hdr_rgb_gold_portra_rec2020448×256 48.7 KB](/uploads/short-url/uSvyZ4oz3JcdEe7tKQJd01j4ynn.png?dl=1)

Everything looks rather smooth.

Maybe we are boosting too much the saturation in the sim (although I find the saturation levels of the images pleasing), or the saturation achievable in physical prints prints cannot fit very well in the sRGB gamut and we get easy clipping. Possibly a combination of the two.

---

## #115 **** (@ZeroEcks) · 2025-02-25 23:14

Thanks for the great work, I played with this and the ART integration. I found it to be very exciting.

The only issue I noticed that stood out was using the agx_emulsiom GUI, being uncolour managed, on macos gives significantly different gamma / contrast when saving a layer compared to the viewing window. Unfortunately this is a bit of a blocker for actually using it much, but it’s somewhat fixable with adjusting the black point and contrast afterwards.

I think these simulations could be a real killer feature for open source photography and I am excited for the possibilities, such as exporting negatives I can use my regular film workflow on, in an attempt to unify my workflows. I also think the grain and halations are quite realistic and finally solve that pixels shouldn’t be the finest unit of detail in an image shot on film.

---

## #116 **Bob** (@PhotoPhysicsGuy) · 2025-02-25 23:17

> **@arctic** (帖子 #114):
> or the saturation achievable in physical prints prints cannot fit very well in the sRGB gamut and we get easy clipping. Possibly a combination of the two.

Maybe it was Daniele Siragusano who once showed a chromaticity plot of projected print film?! I actually can’t remember who it was, maybe it was Troy Sobotka.

BUT it was surprisingly large, almost reaching blue and red corners of the visible locus.

The dyes in the print can be dense enough in two channels that the resulting Blue and Red colors basically only transmit light of the edges of the visible spectrum.

So yes, far greater gamut than sRGB at least in the blues and reds.

But I guess you can try yourself by plugging the test image not into the negative exposure part of your pipe but at the end to see the extent of your spectral-print-gamut in terms of xy-chromaticity plane.

EDIT: (I know this is anecdotal, but I am trying to find the chromaticity plot…but I can’t.)

---

## #117 **jo** (@hanatos) · 2025-02-26 16:09

some initial images with grain:

this is the digi clean, for reference:

[[![2025-02-26-165519_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/6/564aad62c5b56c0d382dd030d99068fcd540fe03_2_690x388.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/6/564aad62c5b56c0d382dd030d99068fcd540fe03_2_690x388.png)

2025-02-26-165519_hyprshot2160×1215 970 KB](/uploads/short-url/cjn3Ae0t6nP76aUbJ2bKTRENPl9.png?dl=1)

and here with grain applied:

[[![2025-02-26-165530_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/c/fcc86d00078661a1f961caac64e699984fe3cd63_2_690x388.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/c/fcc86d00078661a1f961caac64e699984fe3cd63_2_690x388.png)

2025-02-26-165530_hyprshot2160×1215 1.03 MB](/uploads/short-url/A4dJqV9fwlO6KK3AwEDPItobAnV.png?dl=1)

this is grain by layer, i.e. showing grain only for one of the three layers and the other two develop digi clean:

[[![2025-02-26-165549_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/3/c31ebcc062cae72f49e3ddc96522b85708a6d92b_2_690x388.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/3/c31ebcc062cae72f49e3ddc96522b85708a6d92b_2_690x388.png)

2025-02-26-165549_hyprshot2160×1215 990 KB](/uploads/short-url/rQ6XAye1l4VZC2EFRJETmQKiikX.png?dl=1)

[[![2025-02-26-165557_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/5/1589ef8ce43ef6e2b30fb9b3eeaed3db4010c4f3_2_690x388.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/5/1589ef8ce43ef6e2b30fb9b3eeaed3db4010c4f3_2_690x388.png)

2025-02-26-165557_hyprshot2160×1215 1.01 MB](/uploads/short-url/34xyh8WEna4qTrIW17AquvtlXGj.png?dl=1)

[[![2025-02-26-165607_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/5/7514bc1a236295735738abb043c9df35812f12d2_2_690x388.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/5/7514bc1a236295735738abb043c9df35812f12d2_2_690x388.png)

2025-02-26-165607_hyprshot2160×1215 1.01 MB](/uploads/short-url/gHKhRq3zE8eScdOPXlWqSECElZo.png?dl=1)

i just took the grain colour/layer area multipliers from the agx gui. my mathematics are not super clean, i hope to not get caught with it

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 on the bright side it is only moderately slower with grain applied. went up from 25 to 28ms for full res.

i find super cool how the grain contributes to the image and makes it appear sharper.

next: make option to upscale 2x or 4x work, and then implement DIR.

---

## #118 **Chris E** (@elstoc) · 2025-02-26 16:30

> **@hanatos** (帖子 #117):
> i find super cool how the grain contributes to the image and makes it appear sharper.

Exactly what I thought when I saw your images. Even though, when you look at both, the original is obviously sharper (e.g. the eyelashes)

---

## #119 **Bastian Bechtold ** (@bastibe) · 2025-02-26 16:49

> **@hanatos** (帖子 #117):
> i find super cool how the grain contributes to the image and makes it appear sharper.

I sometimes add noise to an image if it appears too soft for printing. A textured paper has a similar effect.

---

## #120 **jo** (@hanatos) · 2025-02-26 19:19

oh man, i just have to say it again… this simulation is soo incredibly cool. i just spent an hour easy just converting a bunch of pictures. the most random shots turn into magic with the filmsim applied… skin tones are deep and shadows exciting… rolloff is soft and just right…

the only thing i struggle with is white balancing, i’ll probably convert the json/list of white balance weights to some vkdt presets that change with film/paper combination. in case anyone wants to test my WIP, vkdt git master has it. ([docs here](https://jo.dreggn.org/vkdt/src/pipe/modules/filmsim/readme.html), you’ll need the `filmsim.lut` data file and then apply the `filmsim.pst` to any image you’d like: press `ctrl-p` in darkroom mode, type `filmsim` and then `enter`).

---

## #121 **** (@mikae1) · 2025-02-26 21:10

> **@hanatos** (帖子 #120):
> oh man, i just have to say it again… this simulation is soo incredibly cool.

I very much share your excitement! I sent early fan PMs to [@arctic](/u/arctic) after watching his cryptic PlayRaw contributions for months.

[![:smiley:](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)

 [This example](https://discuss.pixls.us/t/cabo-santa-maria-boa-vista/43527/9) really caught my eye in May.

Sadly, I haven’t been successful getting it to run on my Fedora based Aurora installation using `pip` yet, so for now I just wait for your posts in this thread.

[![:smiley:](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)

 Saw a recommendation for `uv`. Hope to try that this weekend! Perhaps your vkdt implementation can make it more accessible to Python imbeciles like me.

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

> **@hanatos** (帖子 #120):
> i just spent an hour easy just converting a bunch of pictures. the most random shots turn into magic with the filmsim applied… skin tones are deep and shadows exciting… rolloff is soft and just right…

Yes, the roll-off looks insanely good in many of the examples I’ve seen. And regarding the colors… We shouldn’t forget that Kodak spent a century perfecting their colors. Their aim was not only to have an accurate rendition of colors, but also an eye pleasing one.

I genuinely do *not* think that the excitement for film is based on pure hype or trend. Of course there’s also the element of physically, but people spend an inordinate amount of time trying to achieve a proper film colors in Lightroom only finish it off with Adobe’s monochrome grain…

It kind of surprises me that after ~19 years of Lightroom and ~15 years of darktable, we’re still stuck with monochrome grain for color images and no attempts at replicating the other properties of film (like halation). Meanwhile the cine graders get all the shiny toys. There’s Filmbox and Dehancer and DaVinci Resolve recently got an amazing native Film Look Creator. The aim of the Film Look Creator is not to simulate any specific film, but to give film-like results with lots of control. In many ways it looks quite similar to what I’m seeing in this thread.

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/3/83ccb6c8d8d0ce0796518bbeceb0fbdaecac499a_2_690x716.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/3/83ccb6c8d8d0ce0796518bbeceb0fbdaecac499a_2_690x716.png)

image1230×1278 98.1 KB](/uploads/short-url/iNX94AF72Ozi2KcigTxpB70MqEy.png?dl=1)

After some years of using darktable I’m *somewhat* OK with the tools I have at hand. I have, for the past 12 years I’ve used workflows that try to mimic a Portra 400 NC or VC look digitally, previously in Lightroom with VSCO presets/profiles and now in darktable with G’MIC sRGB Cube LUT.

It does *not* replicate the subtleties of film like what I’m seeing in [@arctic](/u/arctic)’s PlayRaw examples though.

If [@arctic](/u/arctic)’s filmsim comes to open source software I think we could expect some proper excitement for open source alternatives to Adobe’s products. There’s really nothing like it in the stills software world and still the demand seems huge.

> **@hanatos** (帖子 #117):
> i find super cool how the grain contributes to the image and makes it appear sharper.

This is an interesting observation. As I said earlier in this thread it’s a great way of making upsampling/interpolation artifacts vanish. We partially judge the sharpness of the underlying image based on the sharpness of the “grain layer”.

---

## #122 **Andrea** (@arctic) · 2025-02-27 00:30

> **@ZeroEcks** (帖子 #115):
> The only issue I noticed that stood out was using the agx_emulsiom GUI, being uncolour managed, on macos gives significantly different gamma / contrast when saving a layer compared to the viewing window. Unfortunately this is a bit of a blocker for actually using it much, but it’s somewhat fixable with adjusting the black point and contrast afterwards.

Yeah, sorry about that, this is really a minimal one-file gui solution that kinda works. You can try to match your monitor/os profile with the output profile of the sim. [@NateWeatherly](/u/nateweatherly) above in the thread was talking about having DisplayP3 as an ok solution to work with a ok color managed preview. Try to have a look into that! Here is the link to the post:

> **@NateWeatherly** (帖子 #56):
> On a Mac, just having an ImageP3 or DisplayP3 output ICC profile would come pretty close to having a color managed preview.

Also I am not super keen at having this as a final solution. I think there are much better human interfaces in other softwares (vkdt, darktable, rawtherapee, art…), so there is probably no need to rebuild everything. I see this as a tech demo that I am very comfortable at hacking, and go crazy with details. If it is going to be a viable solution for actual doing some work I could put together something better in the future. For now my focus has been the engine and the “look”. But thank you for the critic!

[![:smiley:](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)

 It is in my mind.

---

## #123 **Andrea** (@arctic) · 2025-02-27 00:41

> **@hanatos** (帖子 #117):
> went up from 25 to 28ms for full res.

I am jawdropped, even if it is a simplified version

[![:grin:](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)

 …3 ms is probably close to 4 orders of magnitude faster of what it takes in my hacky python for just grain generation.

> **@hanatos** (帖子 #117):
> i find super cool how the grain contributes to the image and makes it appear sharper.

I absolutely agree on this, I love the idea of upscaling and adding grain. And not being able to see the pixels when looking closer! Usually pixel-peeper is used with a negative connotation, but I guess grain-peeper only has a hipster positive aura.

> **@hanatos** (帖子 #117):
> my mathematics are not super clean, i hope to not get caught with it

He he, I think it looks already extremely good! If you need a bit of background on my assumptions about the grain model I will write something. If it helps!

[![:blush:](https://discuss.pixls.us/images/emoji/apple/blush.png?v=12)](https://discuss.pixls.us/images/emoji/apple/blush.png?v=12)

> **@hanatos** (帖子 #120):
> i just spent an hour easy just converting a bunch of pictures.

I am also guilty of this, sometimes I wanted to work on it, but I just got sidetracked to try endlessly on random pics.

> **@hanatos** (帖子 #120):
> the only thing i struggle with is white balancing, i’ll probably convert the json/list of white balance weights to some vkdt presets that change with film/paper combination. in case anyone wants to test my WIP, vkdt git master has it.

The way I create the filter neutral values is to fit a sigle gray pixel ([0.184,0.184,0.184]) in the input to obtain the same gray value as output (I actually fit Y filter, M filter, and print exposure). I find the filter neutral values quite sensitive to the pipeline, so not sure they will hold exactly. If they do that would be amazing.

I had a quick look to the code, and I am honored to see this effort, I will try to understand more. And I will try to run it on my desktop, with GPU, that is just taking dust lately.

---

## #124 **Olivier** (@olliwa) · 2025-02-27 01:32

works on win11 too

[![:+1:](https://discuss.pixls.us/images/emoji/apple/+1.png?v=12)](https://discuss.pixls.us/images/emoji/apple/+1.png?v=12)

just unzip last release

just two corrections to create *filmsim.lut*

```
pip install -r requirements.txt
...
cd agx_emulsion/data/profiles

```

---

## #125 **Andrea** (@arctic) · 2025-02-27 01:59

Great comment [@mikae1](/u/mikae1)! If you need any help with the python part let me know.

> **@mikae1** (帖子 #121):
> We shouldn’t forget that Kodak spent a century perfecting their colors. Their aim was not only to have an accurate rendition of colors, but also an eye pleasing one.

I 100% agree here, and I hope to dig more and try to understand what are the general criteria in the spectroscopical data that encodes that, for now it feels something intangible, but there might be some way to rationalize at least partially what is going on.

> **@mikae1** (帖子 #121):
> The aim of the Film Look Creator is not to simulate any specific film, but to give film-like results with lots of control. In many ways it looks quite similar to what I’m seeing in this thread.

Having a general tool not really dependent on ununderstood knowledge baked in the spectroscopical data sounds super cool!

Just for fun I made a comparison with some images I found on my computer from the playraw you referenced, all using the same underlying data. I processed it a few times over the last months, at different stages. They are edited independently (color balance do not exactly match), but I think they illustrate quite well the evolution of the sim.

[[![sea_side](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/e/9e6bb774262cb644c5cec0b6a894e65ceaebe97e_2_330x220.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/e/9e6bb774262cb644c5cec0b6a894e65ceaebe97e_2_330x220.png)

sea_side1920×1281 4.43 MB](/uploads/short-url/mBsdLOzCUl8EYRim2MY7wgWd6YC.png?dl=1)

[[![sea_side2](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/4/04c4474ee7924311bc44bcd70a821aecc6428632_2_330x220.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/4/04c4474ee7924311bc44bcd70a821aecc6428632_2_330x220.png)

sea_side21920×1281 4.43 MB](/uploads/short-url/GaqX6xDrSS7T4sqKVUV2v05Q1I.png?dl=1)

[[![sea_side_3_dir_couplers](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/2/d2efabc7f0ce44d302f28635876e13918b894455_2_330x220.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/2/d2efabc7f0ce44d302f28635876e13918b894455_2_330x220.png)

sea_side_3_dir_couplers1920×1281 3.76 MB](/uploads/short-url/u61LdxaEk0mPBZcvHMDlkEKwoDz.png?dl=1)

[[![sea_side_4_large_gamt](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/b/fb11ae32a1c925354d70140288ad9f5008b2846a_2_330x220.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/b/fb11ae32a1c925354d70140288ad9f5008b2846a_2_330x220.png)

sea_side_4_large_gamt3000×2002 10.4 MB](/uploads/short-url/zP3IY1NXUfoQGyBsOe5roEv5q30.png?dl=1)

In order:

(a) original play raw submission

(b) addition of more refined masking couplers

(c) early version of dir couplers

(d) the current default output of the `large-color-gamut` branch, from (c) we got new more effective dir couplers, plus new hanatos’s spectral upsampling (and much more stuff). Only negative/print exposure changed from default.

All with Kodak Portra 400 and Kodak Ektacolor Edge.

And oh man… I also have to say again that I am amazed by the subtle but satisfying changes the large color gamut input is bringing to the table.

[![:star_struck:](https://discuss.pixls.us/images/emoji/apple/star_struck.png?v=12)](https://discuss.pixls.us/images/emoji/apple/star_struck.png?v=12)

Since I cannot get enough, here is another comparison shot from [signatureedits.com](http://signatureedits.com), with everything default (Kodak Gold and Supra Endura). Input in 32bit linear ProPhoto RGB.

(left) darktable basic edit, (center) mallett2019, (right) hanatos2025

[[![Signature Edits Free RawsIMG_5824](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/6/c6d1c9ce48945a4b290110428cacf05e852da719_2_220x330.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/6/c6d1c9ce48945a4b290110428cacf05e852da719_2_220x330.jpeg)

Signature Edits Free RawsIMG_58241998×3000 825 KB](/uploads/short-url/smQ0wJQVrWx5vGregBnBn48oO3n.jpeg?dl=1)

[[![mallett2019_gold_supra_default](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/e/2ed8570831a6170b0b209b7cbfb149207ff06d9b_2_220x330.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/e/2ed8570831a6170b0b209b7cbfb149207ff06d9b_2_220x330.png)

mallett2019_gold_supra_default1998×3000 10.6 MB](/uploads/short-url/6Gpt8f0SujtfCr2538Hr073sABB.png?dl=1)

[[![hanatos2025_gold_supra_default](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/2/12dbcaf97f48f794fffb02eced4b5cb6f22655ab_2_220x330.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/2/12dbcaf97f48f794fffb02eced4b5cb6f22655ab_2_220x330.png)

hanatos2025_gold_supra_default1998×3000 10.4 MB](/uploads/short-url/2GPuUj60yogY6M901TJMDrnp5Dt.png?dl=1)

Even trying to match the two film sim better, i.e. with the enlarger filters, I cannot really get them feeling the same. The darktable ultra basic edit is with same white balance, using sigmoid with contrast 2, and color balance rgb with 30% global vibrance.

---

## #126 **Andrea** (@arctic) · 2025-02-27 03:21

> **@PhotoPhysicsGuy** (帖子 #116):
> Maybe it was Daniele Siragusano who once showed a chromaticity plot of projected print film?! I actually can’t remember who it was, maybe it was Troy Sobotka.

Uh interesting! I tried to have a quick look on scholar but no luck.

I found this generic data from the books I have. And indeed it seems to be pretty wide, especially red-blue sides.

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/4/54b5cb368b764e77327c9f83d5b5bedf035426c8.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/4/54b5cb368b764e77327c9f83d5b5bedf035426c8.png)

image901×495 26.2 KB](/uploads/short-url/c5nB8kczby7wqBLpqqPL3iML88M.png?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/9/c96b7dc58f3c8fc0286f6a05a0ee8a53e2d7a42e.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/9/c96b7dc58f3c8fc0286f6a05a0ee8a53e2d7a42e.png)

image723×418 30.7 KB](/uploads/short-url/sJQgMboqAa4U3rrBzMVCW3iCcF0.png?dl=1)

From: The manual of photography photographic and digital imaging (ninth edition), Ralph Jacobson, Sidney Ray, Focal Press, 2000, page 388-390.

> **@PhotoPhysicsGuy** (帖子 #116):
> But I guess you can try yourself by plugging the test image not into the negative exposure part of your pipe but at the end to see the extent of your spectral-print-gamut in terms of xy-chromaticity plane.

This is also quite interesting, haven’t tried to input images just for printing, or in any other middle step of the pipeline. It should not be too difficult, I guess I could interpret the linear RGB values as effective exposure of the print paper and compute everything from there.

---

## #127 **jo** (@hanatos) · 2025-02-27 10:22

> **@arctic** (帖子 #123):
> If you need a bit of background on my assumptions about the grain model I will write something. If it helps!

yeah we should probably discuss this some. for now i’m just considering “a lot” of grains inside one pixel, such that the spatial white noise distribution characteristics turn into some gaussian filtered white noise (a bit more blue). this is like the non-uniformity of grain numbers as seen through each pixel. now really i’d like to use some binomial/poisson random variate with expectation = developed density to sample which of these grains turn. whatever i did was probably wrong because it just floods the whole image with exorbitant amounts of noise. there’s something fundamentally awkward about the poisson distribution that i can never quite find intuitive… this fact that every particle brings their own variance… so more photons per pixel mean more variance. quite the opposite of a monte carlo estimator! anyways the number of developed grains per pixel is for now just directly the expectation <span class="math">n\cdot p</span>.

> **@arctic** (帖子 #123):
> The way I create the filter neutral values is to fit a sigle gray pixel ([0.184,0.184,0.184]) in the input to obtain the same gray value as output (I actually fit Y filter, M filter, and print exposure). I find the filter neutral values quite sensitive to the pipeline, so not sure they will hold exactly. If they do that would be amazing.

right. i suppose the differences are subtle but probably exist (i use pretty crude approximations of the YMC filters for instance). i have nelder mead/adam optimisers in vkdt that are in theory able to wrap around a processing graph and fit module parameters to picked colours/loss module output. will try that fitting step and see what happens.

oh one more thing: i don’t use the envelope function. i figured the pipeline does not fluoresce, i.e. the wavelengths don’t exchange energy (other than projecting to cmy/rgb densities in between). in the very end, the scanning step projects to the 1931 CMF which already have the falloff at 400 and 700 nm just like the assumptions of the upsampling routine would be. would you have a particular image and settings for me that showed the cyan issue? i’d like to try and reproduce…

---

## #128 **Bob** (@PhotoPhysicsGuy) · 2025-02-27 11:07

> **@arctic** (帖子 #126):
> I found this generic data from the books I have. And indeed it seems to be pretty wide, especially red-blue sides.

Great! It really looks like those gamuts really exceed the sRGB gamut. I am also *not* claiming that “bigger-gamut = better” but that one has to keep this in mind wrt adjusting DIR-coupler settings.

---

## #129 **jo** (@hanatos) · 2025-02-27 13:56

looking at the couplers and the non local part again. maybe you can explain to me in simple non-python terms what this code is supposed to do

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

it interpolates quite a bit of stuff going back and forth between exposures and densities, and i’m lost.

from what i understand, a 3x3 coupler matrix is constructed, and applied to the (normalised, potentially exposure shifted) density curves by component wise multiplication to the 3 curves. why normalised? isn’t the matrix multiply without normalisation the same? normalisation just for the exposure shift in case it’s non-zero?

then why can you just subtract the result (isn’t that a density?) from the log exposure? and why go from this log exposure to density again? then from density to log_raw_correction? and why linear filter/gauss blur the log exposure correction? shouldn’t we blur linear scene referred light values instead? i assume the radius can be quite large here. and then finally the corrected/blurred log raw is going to density again, via corrected density curves.

this feels like going in circles a fair bit, potentially because it’s easy to write this in python? what’s happening conceptually here?

---

## #130 **Andrea** (@arctic) · 2025-02-27 14:39

> **@hanatos** (帖子 #127):
> yeah we should probably discuss this some. […] now really i’d like to use some binomial/poisson random variate with expectation = developed density to sample which of these grains turn.

The assumption behind the grain is that each layer has a total area coverable by particles proportional to the density max. Each sub-layer has thus a fraction of this area.

I am using a compound “binomial(poisson, p)”. Poisson for the xy point process of the particles across the planes, i.e. how many particles end up in each pixel bucket. Binomial for the probability of development (p), i.e. proportional to density/density_max. In reality the particles are not really random across the surface, so I added a simple saturation model to take into account the packing, i.e. reduced variance compared to poisson because occlusion. I do this by faking a larger amount of particles that reduces the relative variance, and by scaling the density at the end.

There is a smaller complication about fog. There is a density minimum that is always developed even without light exposure and we need to take that into account.

By the way, I made some code with `numba` that compute approximations of binomial and poisson, and might be closer to your implementation. Essentially I am using a set of approximation to compute the random numbers in different regimes. E.g. for binomial, from direct bernulli sampling to normal. In `agx_emulsion/utils/fast_stats.py` in the `large-color-gamut` branch, possibly useful.

This is the behavior of a single layer.

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/8/e/8e607401872bbd71822ba452262bfcaeeab11983.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/8/e/8e607401872bbd71822ba452262bfcaeeab11983.png)

image584×432 50.3 KB](/uploads/short-url/kjwrWzqwY2q1v6YiXx8Y3kRQ6uT.png?dl=1)

<details>
<summary>
Minimal grain code for one layer, for making also the RMS figure.</summary>

<pre data-code-wrap="python"><code class="lang-python">import scipy
import numpy as np
import matplotlib.pyplot as plt

poisson_rvs = scipy.stats.poisson.rvs
binomial_rvs = scipy.stats.binom.rvs
# beta_rvs = scipy.stats.beta.rvs
n_particles = 1000 # on average per pixel
dmax = 1.0
od_particle = dmax/n_particles

samples = 1000
le = np.linspace(-3, 3, 512) # log exposure
p = scipy.stats.norm.cdf(le) # simple density curve
p = np.tile(p, (samples, 1))

samples_sat = []
uniformity = [0.5, 0.7, 0.9, 0.95]
for i, uni in enumerate(uniformity):
 saturation = 1 - p*uni*(1-1e-6)
 samples_sat_max = poisson_rvs(n_particles/saturation, size=p.shape)
 samples_sat.append(binomial_rvs(samples_sat_max, p)*saturation*od_particle)

seeds = poisson_rvs(n_particles, size=p.shape)
samples_binom_poisson = binomial_rvs(seeds, p)*od_particle
samples_binom = binomial_rvs(n_particles, p)*od_particle # case of perfect ordering
# samples_beta = beta_rvs(p*(n_particles-1), (1-p)*(n_particles-1), size=p.shape)*n_particles*od_particle

plt.plot(le, np.std(samples_binom_poisson, axis=0), label='Binomial(Poisson)')
plt.plot(le, np.std(samples_sat[0], axis=0), label='Binomial(Poisson) with uniformity=0.5')
plt.plot(le, np.std(samples_sat[1], axis=0), label='Binomial(Poisson) with uniformity=0.7')
plt.plot(le, np.std(samples_sat[2], axis=0), label='Binomial(Poisson) with uniformity=0.9')
plt.plot(le, np.std(samples_sat[3], axis=0), label='Binomial(Poisson) with uniformity=0.95')
plt.plot(le, np.std(samples_binom, axis=0), label='Binomial')
# plt.plot(le, np.std(samples_beta, axis=0))
plt.xlabel('Log Exposure')
plt.ylabel('RMS Granularity')
plt.legend()
</code></pre>

</details>

> **@hanatos** (帖子 #127):
> i don’t use the envelope function. i figured the pipeline does not fluoresce, i.e. the wavelengths don’t exchange energy

I didn’t understand this comment about the envelope. What is this envelope in this context?

For sure this test image I created shows the issue.

[gradient_hdr_rgb.exr](/uploads/short-url/dSLvnmpgJjpuS6iuFYksycL2lMe.exr) (390.8 KB)

You can import it both in linear Rec2020 or linear ProPhoto RGB.

(left) interpreted as linear Rec2020, (right) interpreted as linear ProPhoto RGB

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/9/a/9a7e3fd3e24fde1771f9479e5283c387e9987b45.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/9/a/9a7e3fd3e24fde1771f9479e5283c387e9987b45.png)

image630×605 54.2 KB](/uploads/short-url/m2I18FwEY9YVzpEd86tfRk7LS0R.png?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/a/f/afc6471b99473e702711ee7e0c05c5d9ea314ac1.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/a/f/afc6471b99473e702711ee7e0c05c5d9ea314ac1.png)

image630×605 54 KB](/uploads/short-url/p4YmEUgBPMPILSqZE2bNvJulfQl.png?dl=1)

The output is still smooth in a large output color space, so for some reason we are hitting the clipping of the output sRGB hard on the cyan side.

> **@arctic** (帖子 #10):
> image630×628 106 KB image389×389 21.3 KB

Like shown before already in these tests. But why this is happening and if it is expected behaviour of prints it is a different topic. The nice thing is that I don’t remember I have encountered any real world image that I processed in which this was a disturbing issue.

As [@PhotoPhysicsGuy](/u/photophysicsguy) was commenting, by looking at real data, the gamut of print papers is quite large and extends beyond sRGB, also on the cyan side.

---

## #131 **jo** (@hanatos) · 2025-02-27 14:56

ah i meant the band pass envelope function in this image above, explicitly cutting off extreme wavelengths:

 [[![图片224](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/6/06b69d7f293316265e727ce44256329670a16c1b.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/6/06b69d7f293316265e727ce44256329670a16c1b.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/6/06b69d7f293316265e727ce44256329670a16c1b.png)

---

## #132 **Andrea** (@arctic) · 2025-02-27 15:10

> **@hanatos** (帖子 #127):
> i figured the pipeline does not fluoresce,

Indeed there is no fluorescence/phosphorescence, but from my experience there are unpleasant colors, especially reds, when film sensitivities are broader than CIE 1931 CMFs. And there are less of this issues when sensitivities are more spectrally narrow in the visible. So it is not really related to the input-output spectral bounds, but to the way film sees light. I can provide some more examples to support the improvement. But I am also ok to be disproven.

[![:grin:](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)

I will answer later on the couplers, I like the confusion in your comment, it explains perfectly the acrobatics in the code. Trust me, in my mind and notes there is some rationale. But it might crumble after a revision by someone else. I’ll try to explain.

---

## #133 **jo** (@hanatos) · 2025-02-27 18:15

> **@arctic** (帖子 #132):
> I will answer later on the couplers,

no pressure, no rush! i’m just getting carried away here… will look at grain again in the meantime.

i did the ym filter fitting now btw. i had to fit cyan too, but even then some combinations of film and paper turn to negative filter percentages… not very reassuring. this is matching 0.184 input to 0.5*D50 on the output… sometimes i can get more pleasing skin tones (with positive filter weights) when trying to match that directly. anyways, continues to be good fun!

---

## #134 **Andrea** (@arctic) · 2025-02-27 22:01

> **@hanatos** (帖子 #129):
> looking at the couplers and the non local part again. maybe you can explain to me in simple non-python terms what this code is supposed to do

No worries no pressure

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

I tried to write down the reasoning, but it is probably more convoluted that I thought. Anyway here is an explanation attempt of my inspiration, trying to justify the steps.

DIR couplers are chemicals released together with the formation of (coupled with) density and inhibits the development of more density. They diffuse spatially, typically 10-15 micrometers (I don’t a a reference for this for now, just a reasonable guess), one layer is 2-5 micrometer. So they diffuse both across layers and in the image plane. These are very small distances, a bit larger distances than the grain. For reference typical PSFs for sharp lenses are 2-3 micrometers, 5+ for worse ones.

It would be nice to make a small kinetic scheme to simulate proper inhibition kinetics, and integrate the differential equations, but it would be quite computationally expensive I think.

My drastic assumption and reasoning are:

- wathever we do we want to respect the `density_curves` data. They are measured exposing with a neutral illumination the film (d55 or d65), creating density in all layers simultaneously.
- the density is a measure of concentration of developed dyes ([Lambert-Beer law](https://en.wikipedia.org/wiki/Beer%E2%80%93Lambert_law)). Since the proportionality density-concentration depends by the absorption efficiency, I normalized by `max_density` to have a 0-1 quantity of dye comparable in every layer.
- I am first assuming that `density_cmy_0` computed with the original `density_curves` is a first estimate of the density that would form on the layer.
- I now assume that the quantity of DIR couplers generated on a layer is proportional to `density_cmy_0` normalized, because they are formed in a coupled way during development. This is of course an approximation.
- the couplers diffuses across the layers and in space, i.e. gaussian blurring.
- next I am assuming that the development of film and the quantity of density reached in a layer is kinetically controlled given a certain time of development. Thus the density produced on a layer is “velocity of development x time of development” (at least when far from density max). Time of development is fixed. While velocity of development can change with inhibition.
- I am assuming log exposure to be proportional to the velocity of the reaction of the development process (density created per second). Light produces Ag centers, that will speed up the reaction of silver halides + developer → silver (and later → dyes). Locally more density is generated if more Ag centers were created by light. We can further assume that `log_raw` (from the toe intersection) is linear to the amount of Ag centers (or particle with at least an Ag center that can be developed). Within this assumption `log_raw` is a measure of quantity of stuff (latent particles). This is of course another simplification.
- inhibitors slows down locally the development, causing less halide to silver conversion. We can think as inhibitors able to subtract/inhibit Ag centers, i.e. virtually reducing log exposure (`log_raw`). So `log_raw_corrected` is computed as `log_raw` - the quantity of inhibitors present in that layer and position.
- If we would stop here and reinterpolate `log_raw_corrected` with the normal `density_curves` we would reduce the contrast, and our simulation would not match anymore the data. To fix this we can generate a new set of virtual density curves like if inhibitors were not active: `density_curves_0`. These curves are more contrasty, and they give exactly `density_curves` after the inhibitors are applied with neutral illumination to the film. Now our film respect the original data, and the midtones will be essentially unchanged. Saturated colors instead will have less density on the channels with already low density.

Of course we need to make sure that the amount of inhibitors is calibrated to have a reasonable effect. The reason we can subtract `log_raw` with inhibitors coming from normalized density is then this assumption that both things can be interpreted as quantity of stuff (Ag centers/particles with Ag centers and chemicals suppressing Ag centers).

The spatial xy effect of the dir couplers is to increase sharpness. And we apply a blur to couplers amount (coming from density) because we are interpreting them as quantity of stuff moving around.

This is an example of density curves:

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/8/e/8e9a3c6d055150b77d2b6d028601eb7ec2753f8d.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/8/e/8e9a3c6d055150b77d2b6d028601eb7ec2753f8d.png)

image567×432 21.7 KB](/uploads/short-url/klwfuYa4yHZmu7YXHuvQp45MFXf.png?dl=1)

With dir_couplers_amount = 1.0 we get this amount of couplers in the layers:

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/e/cef422a6fe7d990ace4578923ee30117f3f0de31.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/e/cef422a6fe7d990ace4578923ee30117f3f0de31.png)

image567×432 20.9 KB](/uploads/short-url/twNpP44E2u2XQKe4huziIIEB5Kx.png?dl=1)

Green in the middle of the stack receives from two sides.

This is the coupler matrix illustrating the amount of DIR couplers diffused in each layer from the starting one:

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/4/040e60460b198417eb11909a2f6c9946281c256f.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/4/040e60460b198417eb11909a2f6c9946281c256f.png)

image504×435 5.63 KB](/uploads/short-url/zSI32cAaA3OFapVA2k2KICAdwX.png?dl=1)

And these are density curves pre and post appling couplers. Density curves pre-couplers (dashed) are virtual, never really happening on the film:

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/8/58910540660feff587e1bdd13d2e11ad1f96dc03.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/8/58910540660feff587e1bdd13d2e11ad1f96dc03.png)

image567×432 35.5 KB](/uploads/short-url/cDuIMYkVFqerpNgsTmDgiBhoyGv.png?dl=1)

This description might have scientifically unsound bits, and I can probably refine the assumptions to be more correct in the formulations. I think anyway that the final algorithm is a sort of simplest possible one able to produce the inhibition. We can for sure make it more complex and more true to reality.

---

## #135 **Andrea** (@arctic) · 2025-02-27 22:05

Wow great that you can fit filters on the fly. This opens up also the possibility of more drastic changes to the profiles without the fear of loosing a trusted neutral point for the filters.

> **@hanatos** (帖子 #133):
> i had to fit cyan too, but even then some combinations of film and paper turn to negative filter percentages…

Print paper sensitivities are calibrated to work with filtered tungsten light going through typical negatives. Negative filters is probably a sign that things are a bit uncalibrated compared to reality. In the real world everything should be possible with touching the cyan filter much, too.

> **@hanatos** (帖子 #133):
> 0.5*D50 on the output…

I wonder why 0.5 * D50 and not 0.184 * D50 and if it matters.

---

## #136 **jo** (@hanatos) · 2025-02-28 13:30

> **@arctic** (帖子 #130):
> Minimal grain code for one layer, for making also the RMS figure.

excellent, thank you. now if i use 1000 grains per pixel and a binomial on top of my filtered fake poisson i think it starts to look much better. the binomial resolves some of the overly blue noise regular look. i may think about the saturation part again, didn’t model this yet.

> **@arctic** (帖子 #135):
> Print paper sensitivities are calibrated to work with filtered tungsten light going through typical negatives. Negative filters is probably a sign that things are a bit uncalibrated compared to reality.

apparenly it’s just very sensitive to the YMC filters. i replaced these with some smoother version and re-ran the fit, now everything is positive in <span class="math">[0,1]</span> as expected. i would still say that i have some yellow cast issue with the `kodak supra|portra endura` . maybe that’s my crude filter approximation still.

> **@arctic** (帖子 #135):
> I wonder why 0.5 * D50 and not 0.184 * D50 and if it matters.

ah i was thinking because it’s a display transform … but you’re right gamma will go on top after that. let me re-run with 0.184 and see what happens.

(thinking about the couplers…)

---

## #137 **Jiyone** (@Jiyone) · 2025-02-28 17:11

I wonder if you will add anytime soon some black and white film and B&W paper, with the ilford multi-grade having different layers with different density.

---

## #138 **nosle** (@nosle) · 2025-02-28 22:21

In addition to [@Jiyone](/u/jiyone) question above, how complicated is it to add further sims? Is the data for making more available,?

Does anyone know how different the nc portras were to the newer prefix less versions?

---

## #139 **** (@mikae1) · 2025-02-28 22:36

> **@nosle** (帖子 #138):
> In addition to @Jiyone question above, how complicated is it to add further sims? Is the data for making more available,?

Here I guess:

> **@arctic** (帖子 #34):
> My sources for technical documents have been these websites: Index of /docs/film, Photographic & Darkroom Products by Brand, Browse The Analog Film Stock Library | Filmtypes, https://analogfilm.space/.

---

## #140 **** (@mikae1) · 2025-02-28 22:39

> **@arctic** (帖子 #125):
> (d) the current default output of the large-color-gamut branch, from (c) we got new more effective dir couplers, plus new hanatos’s spectral upsampling (and much more stuff). Only negative/print exposure changed from default.

Yes, looks good indeed! I get stuck on the “greenery” in the lower edge of the picture. Also the ship wreck shadows. It looks so distinctly filmic (and not in the filmic rgb sense

[![:grinning:](https://discuss.pixls.us/images/emoji/apple/grinning.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grinning.png?v=12)

).

> **@arctic** (帖子 #125):
> Even trying to match the two film sim better, i.e. with the enlarger filters, I cannot really get them feeling the same. The darktable ultra basic edit is with same white balance, using sigmoid with contrast 2, and color balance rgb with 30% global vibrance.

What’s your take on mallett2019 vs. hanatos2025? I’ve been on the road and judging comparisons from my phone display, but I believe I prefer hanatos2025 in almost every case.

> **@arctic** (帖子 #125):
> Having a general tool not really dependent on ununderstood knowledge baked in the spectroscopical data sounds super cool!

Yeah, made me think about what you said somewhere earlier in the thread about not being based on measurements but technical documents. Also, I guess at some point the films will have to be named a bit differently. Godak Bortra?

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

---

## #141 **Andrea** (@arctic) · 2025-02-28 23:41

> **@hanatos** (帖子 #136):
> apparenly it’s just very sensitive to the YMC filters. i replaced these with some smoother version and re-ran the fit, now everything is positive in [0,1] as expected. i would still say that i have some yellow cast issue with the kodak supra|portra endura . maybe that’s my crude filter approximation still.

Kodak portra and supra endura shares the same sensitivities (and dye diffuse densities). They are sister papers with just different contrast. In my experience they are also the most prone to show color issues in the development of the model, and they are the ones that kept giving inconsistent results for longer, until I started added more physically meaningful filters and illuminants, etc…

Comparing the sensitivities, they have quite a lot of crosstalk blue-green. Especially the green sensitivities are very blue-shifted compared to others. So my guess is that the filters are pretty critical in the transition at 500 nm for portra (and supra).

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/3/e/3e3983899737cdff8b063639b2fd2b2793b841f6.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/3/e/3e3983899737cdff8b063639b2fd2b2793b841f6.png)

image596×455 55.6 KB](/uploads/short-url/8SsPcYdHE38Ld5fdziUyZxtTMVM.png?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/4/8/482c0b3819d4545b683637916c46ce48921fe060.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/4/8/482c0b3819d4545b683637916c46ce48921fe060.png)

image596×455 53.8 KB](/uploads/short-url/aisJXG6GA4fVGJHw9vNzQlu0KwE.png?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/1/01e7c62389d887af7cc270692364e9d62245784c.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/1/01e7c62389d887af7cc270692364e9d62245784c.png)

image596×455 52.9 KB](/uploads/short-url/gR39MvuzByqecXO0QV321k6msY.png?dl=1)

Portra (and supra) have also the best skin tones of the bunch, and they are different in this by the rest I tried. I started wondering if I should try different filter sets than the generic colorimetric ones I got from Thorlabs. Maybe there are purposedly designed dichroic filters for color enlargers with even better performances?

---

## #142 **Andrea** (@arctic) · 2025-03-01 00:00

> **@Jiyone** (帖子 #137):
> I wonder if you will add anytime soon some black and white film and B&W paper, with the ilford multi-grade having different layers with different density.

This is definitely in my interest and long plan.

[![:star_struck:](https://discuss.pixls.us/images/emoji/apple/star_struck.png?v=12)](https://discuss.pixls.us/images/emoji/apple/star_struck.png?v=12)

 I love black and white grainy images!

I did already explore a bit in the past black and white sim of grain (some very old example with simple models of grain [Embrace the noise! - #20 by arctic](https://discuss.pixls.us/t/embrace-the-noise/17248/20) + a few posts in the later year/s). The current grain model is more complex and multilayered, with proper density curves. Also the addition of the printing step should add better rolloff of grain.

I am very curios to experiment with multi-grade paper and push-pull development, since there are a lot of curves for this. It is super exciting stuff! I need some time for that of course. I just have also a full time job

[![:laughing:](https://discuss.pixls.us/images/emoji/apple/laughing.png?v=12)](https://discuss.pixls.us/images/emoji/apple/laughing.png?v=12)

, but I would love to spend so much more time on working on these models.

---

## #143 **Andrea** (@arctic) · 2025-03-01 00:09

> **@nosle** (帖子 #138):
> In addition to @Jiyone question above, how complicated is it to add further sims? Is the data for making more available,?
Does anyone know how different the nc portras were to the newer prefix less versions?

As [@mikae1](/u/mikae1) pointed out, there is quite a lot of data sheets available around. Making a profile is not simply getting the curves (in an accurate way), but there is a process of unmixing of the channels and adjusting to make sure that the output is ok. Plus most of the time dye diffuse densities are not available for separate CMY channels, and they need to be reconstructed in a sound way that respect the data that is available. For now only Portra really worked great almost out of the box, all the other negatives required more or less touchups (in a minimal fitting way).

Print paper is more straightforward to profile because usually does not have colored coupled dyes and it is a bit easier to predict. Fujifilm does not publish characteristic density curves for paper, though.

I got all the data manually from the PDFs using WebPlotDigitizer. And then manually worked on them to make sure they would behave properly (mainly I made sure they are able to reproduce a ramp of neutral gray without eccessive tints, adding minimal changes to the density curves). There is some code to make the profiles, but data should be evaluated case by case, because you never know when it is going to be inconsistent and with errors.

---

## #144 **Andrea** (@arctic) · 2025-03-01 00:16

> **@mikae1** (帖子 #140):
> What’s your take on mallett2019 vs. hanatos2025? I’ve been on the road and judging comparisons from my phone display, but I believe I prefer hanatos2025 in almost every case.

The algorithm of spectral upsampling of [@hanatos](/u/hanatos) is so much better in any possible way when compared to [Mallett2019]. And it adds just very little computational overhead and some complexity. It works on the full visible locus and allows for more saturation on the input data. When judging subjectively the results, in my opinion it adds distinct “depth and realism” (in a physically based sense).

I completely stopped using the sRGB workflow, and this should tell something on my take.

[![:slightly_smiling_face:](https://discuss.pixls.us/images/emoji/apple/slightly_smiling_face.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slightly_smiling_face.png?v=12)

---

## #145 **Andrea** (@arctic) · 2025-03-01 10:32

Hi all! Just merged the `large-color-gamut` branch, that include the new spectral upsampling method. Now the recommended workflow is to export RAW files to a large linear RGB space, such as ProPhoto RGB or Rec2020, and use `hanatos2025` as spectral upsampling method. All of these are new defaults.

Among other changes:

- a few functions were rewritten with Numba for increased efficiency, and iterate faster in this testing/dev phase of the model. Now a 6 MP simulation (3000x2000 pixels) takes 10 seconds on my laptop. An update of the gui in preview mode takes 1-2 seconds, now with grain and halation disabled until `compute_full_image` is clicked. Numba accelerated functions include:
 <ul>
 <li>3D and 2D lut cubic interpolation
- approximate random number generators for poisson, binomial, and lognormal
- linear interpolation faster than `np.interp` for larger images

</li>
<li>added pyFFTW as requirement, for performing faster parallel FFT gaussian filtering for halation. Usually has pretty large kernels</li>
<li>add a spectral band pass filter to the camera (UV and IR cuts), not really meant to be changed but exposed in the GUI to play with</li>
</ul>

Since a few things changed, if you happens to try it and find issues, let me know. Thanks!

---

## #146 **** (@ChrisB) · 2025-03-01 17:22

> **@arctic** (帖子 #68):
> Nice Lego render. Do you think the Lego figurine in the background has some red gradient issues? Or is this image used to reveal anything in particular?

The lego bricks in the foreground and the background lego figure use ACEScg primaries. A bit like the dragon render from [@liam_collod](/u/liam_collod) the idea to see how “robust” the image formation is.

About the gradient, I think this is indeed one of the critical aspects of a good image formation. I wanted to write a small post about it.

I am curious to test the app again as it seems to have changed a lot over the last weeks !

---

## #147 **** (@ChrisB) · 2025-03-01 17:52

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/7/97744216f1a0e216d27033fd2b47ae27d0ff331f_2_690x388.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/7/97744216f1a0e216d27033fd2b47ae27d0ff331f_2_690x388.jpeg)

image1173×660 157 KB](/uploads/short-url/lBPb9VC9vPL99PNjChCmGwuATRJ.jpeg?dl=1)

Nice updates on the app ! I just drag and drop an exr, pick the colorspace and that’s about it ! Cool !

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/a/7af8b402be64da0a5f4362442220e0d85078a63d_2_690x385.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/a/7af8b402be64da0a5f4362442220e0d85078a63d_2_690x385.jpeg)

image957×535 67.6 KB](/uploads/short-url/hxR5UZJr5gHgfOwftjXqo5HylVr.jpeg?dl=1)

---

## #148 **Cameron Rad** (@cameronrad) · 2025-03-01 19:21

It might just be my setup, but unfortunately I can no longer run it on my MacOS ARM (M2 Ultra) system. I think it might be something with Numba. When I try to run the command [@liam_collod](/u/liam_collod) provided above, I get this as a result.

```
Numba workqueue threading layer is terminating: Concurrent access has been detected.

 - The workqueue threading layer is not threadsafe and may not be accessed concurrently by multiple threads. Concurrent access typically occurs through a nested parallel region launch or by calling Numba parallel=True functions from multiple Python threads.
 - Try using the TBB threading layer as an alternative, as it is, itself, threadsafe. Docs: https://numba.readthedocs.io/en/stable/user/threading-layer.html

```

I tried updating some sections of the code and got a little bit further, then ran into this error.

` ValueError: No threading layer could be loaded. HINT: One of: Intel TBB is required, try: $ conda/pip install tbb OR Intel OpenMP is required, try: $ conda/pip install intel-openmp`

I don’t think those can be installed on a ARM based Mac.

---

## #149 **Andrea** (@arctic) · 2025-03-01 19:44

Ok! thanks for testing it.

Could you try to put this on the very top of the `main.py`?

```
import os
os.environ["NUMBA_THREADING_LAYER"] = "TBB"

```

I read that it could fix this kind of issues. If numba is problematic I might want to make it as an optional acceleration, or learn how to use it in a more safe way.

---

## #151 **Cameron Rad** (@cameronrad) · 2025-03-01 19:59

Unfortunately it doesn’t work for my setup. I get an error telling me to install tbb.

```
ValueError: No threading layer could be loaded.
HINT:
Intel TBB is required, try:
$ conda/pip install tbb

```

If I add tbb to the requirements or try to install it manually with pip, it doesn’t work as there doesn’t seem to be any wheels available for my system for tbb.

```
╰─▶ Because all versions of tbb have no wheels with a matching platform tag (e.g., `macosx_15_0_arm64`) and you require tbb, we can conclude that your
 requirements are unsatisfiable.

 hint: Wheels are available for `tbb` (v2022.0.0) on the following platforms: `manylinux_2_28_x86_64`, `win_amd64`

```

---

## #152 **Y** (@Y69) · 2025-03-01 20:02

Yea, got the same issue on Linux. Even after forcing Numba to use Intel TBB and supplying the TBB via `pip install tbb`

[![:confused:](https://discuss.pixls.us/images/emoji/apple/confused.png?v=12)](https://discuss.pixls.us/images/emoji/apple/confused.png?v=12)

---

## #153 **Andrea** (@arctic) · 2025-03-01 20:18

I see, that’s not nice. I will make numba functions optionals if this is really not solvable. I didn’t expect then to break so much

[![:grin:](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)

 sorry for this!

---

## #154 **Y** (@Y69) · 2025-03-01 20:21

Making the thing multi-threaded is a good thing

[![:wink:](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)

---

## #155 **Cameron Rad** (@cameronrad) · 2025-03-01 21:17

I got it temporarily working by doing that I think. I replaced all instances of

`parallel=True` with `parallel=False`.

I also added this to the top of main.py

```
import os
os.environ["NUMBA_THREADING_LAYER"] = "threadsafe"

```

Now it opens up again for me. It’s slow but it opens and runs.

---

## #156 **Cameron Rad** (@cameronrad) · 2025-03-01 22:07

So I went through and started re-enabling `parallel=True` in certain files and trying to narrow down where the issue is happening and I think it’s with `fast_gaussian_filter.py`. Once I enable `parallel=True` in there, I can no longer launch it. Having it enabled in `fast_interp_lut.py` `fast_interp.py` `fast_stats.py` and `fft_gaussian_filter.py` doesn’t seem to cause any issues with launching the app.

I also tested it with removing

```
import os
os.environ["NUMBA_THREADING_LAYER"] = "workqueue"

```

from `main.py` and just changing `parallel=True` to `parallel=False` in `fast_gaussian_filter.py` and it launched.

---

## #157 **Andrea** (@arctic) · 2025-03-02 00:31

Thank you for investigating on this, since with `parallel=False` the gain is less than 2x (compared to roughly 3-4x that was before), i temporarily reverted in the `main` branch to scipy’s `gaussian_filter`. Hopefully it will work more robustly on every platform this way.

[![:+1:](https://discuss.pixls.us/images/emoji/apple/+1.png?v=12)](https://discuss.pixls.us/images/emoji/apple/+1.png?v=12)

---

## #159 **jo** (@hanatos) · 2025-03-02 17:58

> **@arctic** (帖子 #141):
> Portra (and supra) have also the best skin tones of the bunch, and they are different in this by the rest I tried. I started wondering if I should try different filter sets than the generic colorimetric ones I got from Thorlabs. Maybe there are purposedly designed dichroic filters for color enlargers with even better performances?

interesting, yes maybe there are better filters. i have some more or less (rather less) accurate analytic fit to the thorlabs filters. especially the 500nm are problematic for me. i get positive/well behaved filter weights after the optimisation when i overlap magenta and yellow such that they sum to one but cross over at 500nm. if i match your data better, the weights go haywire.

i’m now using a 2856K thungsten lamp, not 3200K, because eyeballing your graph the low values at 400nm and the high at 800 looked more like that to me (no scientific data driven reason). i think maybe my results look better now (?). i also have a bandpass filter, but so far can’t say it made much of a difference.

one thing i noticed when working with portra film/paper is that i can control the “white balance” by playing with film exposure vs. print exposure. maybe this auto exposure part is where my portra looks so different to the agx-emulsion one, because otherwise i get really similar results now (without halation and couplers for now).

---

## #160 **** (@mikae1) · 2025-03-02 20:27

OK, I have just begun to play with agx-emulsion but… This is far beyond my expectations!

[![:exploding_head:](https://discuss.pixls.us/images/emoji/apple/exploding_head.png?v=12)](https://discuss.pixls.us/images/emoji/apple/exploding_head.png?v=12)

 *Good* work!

[![:medal_sports:](https://discuss.pixls.us/images/emoji/apple/medal_sports.png?v=12)](https://discuss.pixls.us/images/emoji/apple/medal_sports.png?v=12)

---

## #161 **Jed Smith** (@jedsmith) · 2025-03-02 22:21

I wonder if there is any spectral response characteristics to be found for Print Film stocks like Kodak 2383. It could be aesthetically interesting to have support for that imaging pipeline in addition to print paper.

---

## #162 **Andrea** (@arctic) · 2025-03-02 22:49

> **@hanatos** (帖子 #159):
> i get positive/well behaved filter weights after the optimisation when i overlap magenta and yellow such that they sum to one but cross over at 500nm. if i match your data better, the weights go haywire.

Great job and interesting to hear. Maybe I should also go back to the filters and try to use something more similar to what works more reliably for you. If you get any more insight I am all ears!

> **@hanatos** (帖子 #159):
> i’m now using a 2856K thungsten lamp, not 3200K, because eyeballing your graph the low values at 400nm and the high at 800 looked more like that to me (no scientific data driven reason).

My reason to use a cooler temperature comes from studying the manual of the Durst M605

[Durst_M605.pdf](/uploads/short-url/euuy2uGObEomDuF4rmE7EC1zphn.pdf) (7.1 MB), where they use a tungsten-halogen lamp that should be cooler than tungsten. I didn’t really try much more to optimize the output.

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/1/21df2edc127265dace2f5fe6ac13efe7066d59ec_2_500x500.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/1/21df2edc127265dace2f5fe6ac13efe7066d59ec_2_500x500.jpeg)

image937×882 225 KB](/uploads/short-url/4PDVhPMvks2KhwGgGdgzgs5x5ve.jpeg?dl=1)

> **@hanatos** (帖子 #159):
> i think maybe my results look better now

Amazing!

[![:sunglasses:](https://discuss.pixls.us/images/emoji/apple/sunglasses.png?v=12)](https://discuss.pixls.us/images/emoji/apple/sunglasses.png?v=12)

For the effect of the band-pass filter I think this image from signatureedits that I posted above also, [vintage red car image](https://www.signatureedits.com/wp-admin/admin-ajax.php?action=useyourdrive-download&account_id=103498887174941726250&id=1IChRf9tEvOljWAOkiav1fG1IX2G-gfEO&dl=1&listtoken=d8b65b66692c59f215d41b174d2a67af), is a very challenging one. Without filters and using kodak portra 400 it is really difficult to get satisfying reds, as with kodak gold 200. Especially the reflections on the top of the hood.

> **@hanatos** (帖子 #159):
> one thing i noticed when working with portra film/paper is that i can control the “white balance” by playing with film exposure vs. print exposure. maybe this auto exposure part is where my portra looks so different to the agx-emulsion one, because otherwise i get really similar results now (without halation and couplers for now).

Even if portra 400 has a lot of latitude, there are shifts with over exposure. In my experience the best look is achieved with the minimal negative exposure that retains dark shadows. Moreover the profiles were optimized using my pipeline (optimization only of `density_curves` aiming for mid gray neutral prints for a range of negative exposures, using a fitting routine).

For portra 400 not much changed compared to the original data. The original profile without further corrections is `kodak_portra_400_au`, while `kodak_portra_400_auc` has a small correction to the density curves. `kodak_portra_400_au` has only the “unmixing” of the density done, and does not depend at all by the `agx-emulsion` pipeline. Note that not all of the `_au` profiles give good results, most of them are affected by heavy color tints in `agx-emulsion`.

---

## #163 **Andrea** (@arctic) · 2025-03-02 22:56

Yes, there are good data available, the [datasheet](https://www.kodak.com/content/products-brochures/motion-picture/KODAK-VISION-Color-Print-Film-2383-3383-technical-information.pdf) looks of good quality with all the necessary data. I agree that print film would be very interesting to try. This already came up in a discussion with [@PhotoPhysicsGuy](/u/photophysicsguy). I added it on the future list of the film stock to profile.

---

## #164 **Cameron Rad** (@cameronrad) · 2025-03-03 07:26

I think it’d be interesting to create a virtual Fuji Frontier scanner model somehow if possible. Then that can maybe be used along with real world tests/scans to validate the results and simulation of film stocks. I believe that’s what VSCO ended up creating. It’s been written about a little bit here:

- [VSCO Film X & The Imaging Lab | VSCO Engineering](https://eng.vsco.co/vsco-film-x-&-the-imaging-lab/)
- [How VSCO Builds Film-Like Smartphone Photo Filters in Its Lab | WIRED](https://www.wired.com/story/vsco-film-photo-filters/)
- [‎Inside VSCO’s Imaging Lab : App Store Story](https://apps.apple.com/us/story/id1445632852)

Here are some patents related to the Fuji Frontier. The first link I believe has a graph with the wavelength LEDs used.

- [US20010026369A1 - Light source device and device for reading original - Google Patents](https://patents.google.com/patent/US20010026369A1/en)
- [US20030081211A1 - Light source device and image reading apparatus - Google Patents](https://patents.google.com/patent/US20030081211A1/en)
- [US6751349B2 - Image processing system - Google Patents](https://patents.google.com/patent/US6751349B2/en)
- [US6067109A - Image reading method - Google Patents](https://patents.google.com/patent/US6067109A/en)
- [US6791721B1 - Image reading device - Google Patents](https://patents.google.com/patent/US6791721B1/en)
- [US6665434B1 - Device, method, and recordium for correcting color imbalance of an image - Google Patents](https://patents.google.com/patent/US6665434B1/en)
- [US4893178A - Simulator for automatic photographic printing apparatus including inversion circuitry and spectral characteristic compensation - Google Patents](https://patents.google.com/patent/US4893178A/en)

---

## #165 **Andrea** (@arctic) · 2025-03-03 21:51

> **@cameronrad** (帖子 #164):
> VSCO Film X & The Imaging Lab | VSCO Engineering
How VSCO Builds Film-Like Smartphone Photo Filters in Its Lab | WIRED
‎Inside VSCO’s Imaging Lab : App Store Story

Reading this gave me a new level of respect for VSCO. They must have a lot of fun with all this characterizations.

> **@cameronrad** (帖子 #164):
> The first link I believe has a graph with the wavelength LEDs used.

Thank you for searching the patent literature.

Having the LED light source spectra is a good start. I guess the most difficult part will be to understand what is the actual data processing pipeline from their RAW scanned file (calibrations/transform matrices/curves… etc). VSCO (and negative lab pro) might solve this by profiling input/output of the scanner with color test charts.

If we find any decent complete source with the methods behind the scanner processing we could attempt something from first principle. I bet it is going to be very hard to find it, though.

I am skimming the patents for hints.

---

## #166 **Andrea** (@arctic) · 2025-03-04 00:21

I have a preliminary first test using Kodak Vision Premier color print film 2393.

I am struggling fitting print filters using my enlarger light source (I will have to change it compared to what RA-4 paper uses, or trying to understand the issue).

The comparison uses Kodak Ultramax 400, that by chance can be fitted.

(left) Kodak 2393, (right) Kodak Portra Endura

[[![ultramax_kodak_2393](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/3/03a0c32f1ef8df8152ce86a178d06e60f910acc7_2_330x490.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/3/03a0c32f1ef8df8152ce86a178d06e60f910acc7_2_330x490.jpeg)

ultramax_kodak_23931998×3000 1.01 MB](/uploads/short-url/w5RAxN7uO1ehevxU8DHqxiGsHZ.jpeg?dl=1)

[[![ultramax_portra_endura](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/1/81969078d071887162aca1eb8b2f9c3ff920de77_2_330x490.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/1/81969078d071887162aca1eb8b2f9c3ff920de77_2_330x490.jpeg)

ultramax_portra_endura1998×3000 949 KB](/uploads/short-url/iuoaVIG7gQ17pnbzGXKizM8YD1Z.jpeg?dl=1)

I notice very deep blacks. Density curves reach almost 6 OD!

I am not sure if we should mix photography film with movie print film. It might be an heretic thing to do.

[![:laughing:](https://discuss.pixls.us/images/emoji/apple/laughing.png?v=12)](https://discuss.pixls.us/images/emoji/apple/laughing.png?v=12)

 But this is what we got for a first test.

---

## #167 **Bastian Bechtold ** (@bastibe) · 2025-03-04 07:23

> **@arctic** (帖子 #165):
> cameronrad:

VSCO Film X & The Imaging Lab | VSCO Engineering
How VSCO Builds Film-Like Smartphone Photo Filters in Its Lab | WIRED
‎Inside VSCO’s Imaging Lab : App Store Story

Reading this gave me a new level of respect for VSCO. They must have a lot of fun with all this characterizations.

</blockquote>
</aside>

I had no idea they were this serious about film simulations. I always had them pegged as a simple preset app, but this gave me a lot more respect for their work!

---

## #168 **jo** (@hanatos) · 2025-03-04 08:14

just wanted to mention here that i had some issues with very saturated/narrow spectra: [Problem with filmsim artifacts · Issue #164 · hanatos/vkdt · GitHub](https://github.com/hanatos/vkdt/issues/164) and share a new upsampling lut. i know agx-emulsion uses dense sampling and some regularisation for better integration, so there might not be any problem. i now use a lut for the spectral upsampling that stops creating narrower peaks just before it reaches the boundary of the spectral locus. as a result the inpainting for non-physical stimuli are also much smoother:

[spectra-em.lut](/uploads/short-url/s3BxvFjjWfUiMEtJjPBfPMbBF0F.lut) (4.0 MB)

---

## #169 **Nate Weatherly** (@NateWeatherly) · 2025-03-04 21:09

> **@arctic** (帖子 #166):
> I am struggling fitting print filters using my enlarger light source (I will have to change it compared to what RA-4 paper uses, or trying to understand the issue).
The comparison uses Kodak Ultramax 400, that by chance can be fitted.

Not sure if this will be helpful or not, but when I was looking into film scanning a while back I came across this Kodak patent for a bandpass filter that can be used to remove problematic portions of the spectrum to make different scanner light sources behave more similarly. Maybe adding this filter will smooth out some of the fitting issues you’ve been having?

[Kodak_Printing_Filter_Patent.pdf](/uploads/short-url/6cf9QUUK2axQ61ThJUaHrynZR23.pdf) (682.1 KB)

---

## #170 **Jakob Andrén** (@jandren) · 2025-03-04 21:53

My idea with my proposed test image was to see how the spectral upsampling behaved when reaching the spectral boundary. I will try to make some tests myself and see if I can provide some insights. The new results using hanatos large gamut spectral upsampling method does work a lot better so its all very promising!

I also realized that another test source could be actual hyperspectral images! Here are some reasonable sources I found so far.

1. Multispectral Image Database from Columbia Imaging and Vision Laboratory, a small but promising selection of images. [CAVE](https://cave.cs.columbia.edu/repository/Multispectral)
2. Large *Hyperspectral imaging dataset* from Bian Lab in China, requires request for access which I haven’t tried but seems like it should work. [GitHub - bianlab/Hyperspectral-imaging-dataset](https://github.com/bianlab/Hyperspectral-imaging-dataset?tab=readme-ov-file)
3. A dataset from Havard, lower quality: [Statistics of Real-World Hyperspectral Images](https://vision.seas.harvard.edu/hyperspec/index.html)
4. Lower quality and resolution dataset captured with a rotating line camera: [danaroth/icvl · Datasets at Hugging Face](https://huggingface.co/datasets/danaroth/icvl) just git clone the link to download.
5. Dataset of faces, again requires request for access which I haven’t tried myself. But faces are of course of interest! [GitHub - hyperspectral-skin/Hyper-Skin-2023: Introducing Hyper-Skin data with 2 types of data pairs: 1. (RGB, VIS), 2. (MSI, NIR)](https://github.com/hyperspectral-skin/Hyper-Skin-2023?tab=readme-ov-file)
6. Finally one that looks very promising and says it should be open but I haven’t been able to access. Adding it here if anyone else manages access it: [GitHub - boazarad/ARAD_1K: ARAD_1K Spectral Image Dataset](https://github.com/boazarad/ARAD_1K)

I also know a local company in Umeå which works with hyperspectral images. I might be able to ask them to take a picture or two with one of their cameras if you have anything specific and doable you had loved to have a hyperspectral test picture of.

---

## #171 **Todd Prior** (@priort) · 2025-03-05 04:40

Ha just a side note we had a student just do a visit with us from the university there. She stayed for a couple of weeks here in Canada. She did a little background on the area and the university in her talk. That looks like a lovely part of the world…

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

---

## #172 **** (@mikae1) · 2025-03-05 08:28

> **@arctic** (帖子 #166):
> I notice very deep blacks.

Looks very nice! Kind of relates to one question I have. I send some pictures for print on Fuji Crystal Archive paper. For these pictures I guess it’d make sense to disable the paper simulation part of agx-emulsion or else they’d be “double papered” with very washed out blacks.

For the files that should be viewed on a screen (uploaded to my website or social media) I’d like to have the paper sim enabled.

Would this even be possible (and is my thinking right)?

**EDIT:** Perhaps one way to go at it would be to assume that I had scanned a paper print. After scanning a paper print in the darkroom days I’d of course set black and white points. Would it be able to provide black and white point controls as a last step in the process in agx-emulsion?

But yeah, I’d still “apply” the “color characteristics” of print paper twice?

I should perhaps also add that I really appreciate agx-emulsion’s inclusion of the paper characteristics. Most other film simulation solutions I’ve come across try to to emulate the color characteristics of a scanner (usually Frontier or Noritsu). Negative film, however, was never meant to be scanned, it was meant to be printed.

---

## #173 **Andrea** (@arctic) · 2025-03-05 11:23

Thanks [@hanatos](/u/hanatos) for the updated lut and sharing the GitHub issue!

I replaced the old one.

Indeed, just looking at the coefficients maps, they look way smoother past the spectral locus.

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/f/2/f218a61672f0c064ea3ef084ac5881895e4a7785.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/f/2/f218a61672f0c064ea3ef084ac5881895e4a7785.png)

image516×149 12.4 KB](/uploads/short-url/yxGmaFZurdcobIOfQhllMYtJ7Fj.png?dl=1)

I compared the old LUT and the new one on the same [flower photo](https://discuss.pixls.us/t/dealing-with-yellow-color-shift/48530) (that I exported to linear ProPhoto RGB).

(left) new LUT - (right) old LUT

[[![flower_fuji400h_crystal_05pe_2Y_10M_newlut](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/2/32c6b72f92b67502b9ec247f95d839565d519c04_2_330x220.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/2/32c6b72f92b67502b9ec247f95d839565d519c04_2_330x220.jpeg)

flower_fuji400h_crystal_05pe_2Y_10M_newlut3000×2000 911 KB](/uploads/short-url/7fbCpZYGniA4GVdOuiR4FgvYN3S.jpeg?dl=1)

[[![flower_fuji400h_crystal_05pe_2Y_10M_oldlut](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/e/0ea46a1c628d325874244fc90355b8b4a75ca970_2_330x220.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/e/0ea46a1c628d325874244fc90355b8b4a75ca970_2_330x220.jpeg)

flower_fuji400h_crystal_05pe_2Y_10M_oldlut3000×2000 911 KB](/uploads/short-url/25wWlh4tQXeDskJ8XwwEwH8rqMw.jpeg?dl=1)

Indeed as you predicted the effect was not very visible.

But that’s still great, probably I could relax a bit the regularization.

---

## #174 **Andrea** (@arctic) · 2025-03-05 11:45

Gotta love these patent sketches!

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/e/b/eb045cca8f0e1c0b33f4a002446d5bb7a89fe220.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/e/b/eb045cca8f0e1c0b33f4a002446d5bb7a89fe220.png)

image1051×286 15.9 KB](/uploads/short-url/xx3yefNaPM604iUhzILQ6FbWOS4.png?dl=1)

I read part of the patent and I agree that they suggest that adding this narrow filtration at approx 500 nm and 610 nm, might help reducing “problematic” regions and normalize output of different lighthouses (light sources + filtration).

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/7/e7466ae24fcfcc1b5a2dc7abef44882d4dc969a7_2_400x290.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/7/e7466ae24fcfcc1b5a2dc7abef44882d4dc969a7_2_400x290.png)

image867×578 26.9 KB](/uploads/short-url/wZXacmfeZQU2HIIV2mgQnqDov8b.png?dl=1)

This is the recommended filter, that also will make the light source slightly warmer, reducing more of the blue part than the red.

I am curious to see also what it will do to Portra film and paper. Especially if it will make it similar to more consumer film and paper.

Thanks [@NateWeatherly](/u/nateweatherly)!

---

## #175 **Andrea** (@arctic) · 2025-03-05 13:03

> **@jandren** (帖子 #170):
> I will try to make some tests myself and see if I can provide some insights.

That would be amazing! Looking forward!

That’s also a great list of repositories!

Using hyperspectral images as references could be interesting and they could be used directly on the input with some hacking. Also, good databases of realistic representative spectra of real objects might be interesting to have.

> **@jandren** (帖子 #170):
> I also know a local company in Umeå which works with hyperspectral images. I might be able to ask them to take a picture or two with one of their cameras if you have anything specific and doable you had loved to have a hyperspectral test picture of.

Oh nice, good friends to have. I don’t have anything specific but it is good to keep in mind. Do you have any more details on their camera? I just want to geek around a bit. I guess there are many solutions to make hyperspectral images.

---

## #176 **Andrea** (@arctic) · 2025-03-05 13:34

> **@mikae1** (帖子 #172):
> But yeah, I’d still “apply” the “color characteristics” of print paper twice?

I guess that the physical interaction of film and print paper during the analog printing process is what we would like to preserve, because it is what encodes part of the look. It definitely encodes color shifts and style, just compare Portra and Endura Premier for example.

I am no expert, but I believe that when printing on photographic paper with modern printers and a digital workflow, the process is optimized for maximal color accuracy. In other words, printers are calibrated to match as good as physically possible the input digital RGB files and the output print colors (when the print is observed under the right conditions). Still physical limits of paper holds, e.g. white and black levels.

The challenge could be rephrased as:

*In `agx-emulsion`, how do we make sure that the exported file, when printed on photographic paper with a modern printer, will match as closely as possible an analog print that we would make from film(+enlarger) that saw the same original scene?*

With this use case in mind we should definitely put some care in deactivating part of the simulation. For example characteristic white/black levels and also glare will be already reproduced on photographic paper even with the digital printing workflow. There is nothing the printer can be about them.

For example I believe that modern printers already take into account viewing glare compensation in the best way, since they are meant to fit in a digital photographer workflow. Images are edited on screen from people that wants good results when they print.

Characteristic curves of print paper meant for analog printing for sure encodes viewing glare compensation (deeper shadows than expected because they will be brightened by glare), so we should remove it and make sure that the image we see on a calibrated screen have the shadows as deep as we would like to have.

So in summary, I think that adding black/white level controls, deactivating random glare, and using viewing glare compensation removal controls, should help in this use case. Maybe we could have an `simulate_for_print` checkbox that does this.

When looking at simulated images on screens we should probably emulate all paper characteristics.

Does this sound alright or am I missing something?

---

## #177 **jo** (@hanatos) · 2025-03-05 16:15

i attempted an implementation of the couplers.

[[![out](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/f/efd0f146cbcc3ce62769eb588e9abc40970dbf69_2_690x332.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/f/efd0f146cbcc3ce62769eb588e9abc40970dbf69_2_690x332.jpeg)

out2244×1080 851 KB](/uploads/short-url/ydvLU49xL0n6gB1bDuYGfY3W13b.jpeg?dl=1)

this is `couplers=0.0, 0.2, ..1.0`. when i look at it on my screen it increases colourfulness quite a bit… only the pixls preview looks all clamped to something. maybe my firefox tries to colour manage and fails or something. so here’s also a wedge with `couplers=0.0,0.5,1.0,1.5,2.0`:

[[![out2](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/5/75556afc993c5d2be12943ff3217526de74fccad_2_690x422.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/5/75556afc993c5d2be12943ff3217526de74fccad_2_690x422.jpeg)

out21765×1080 793 KB](/uploads/short-url/gJYS0s24CtEqhuscEnYMxk5wp9b.jpeg?dl=1)

2.0 goes completely overboard, but that’s fine with me

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

anyhow… i’m using i think your approximations and a few on top now. one simplification is that i’m assuming the released coupler depends on the log exposure, not the density. so it’s kinda linear all the way… no saturation. not sure that breaks in some places… but it happens before the density lookup, adjusting the exposure beforehand, so it still has a soft transition to black/white.

more precisely, i’m assuming measured density curves depending on log-exposure <span class="math">D(e)</span> that have been acquired using a neutral-colour test strip ramp. i’ll assume that to be locally flat/constant, or to diffuse as much into slightly darker as into slightly brighter, so the spatial diffusion kinda cancels out. In this context, the actual corrected log exposure, <span class="math">e_0 = e - K*e</span>, which is reduced by a convolution of the initial exposure with kernel <span class="math">K</span> in space and between layers, this reduces to only interaction with the layer diffusion matrix <span class="math">M</span>, i.e. <span class="math">e_0 = e - M\cdot e</span>. so what i’m claiming is that the actual density-from-exposure function <span class="math">D_0(e)</span> is observed as <span class="math">D(e) = D_0(e - M\cdot e)</span>. this is valid only in the context of the test strip, for neutral-coloured <span class="math">e</span>.

from there i compute the actual density function <span class="math">D_0(e) = D((I-M)^{-1}\cdot e)</span>, which will result in exactly the same result as without the couplers, but only in case <span class="math">e</span> is neutral.

does that make any sense to you at all? too much approximation?

couplers <span class="math">M\cdot e</span> are blurred with a radius relative to the longer side of the picture, turns out to be like 20px in normal raw images, i think. i like the local contrast increase i’m getting from large radii.

as an extra goodie, the display buffer is now mipmapped, so you can see the result of grain more realistically when zoomed out a lot. also the 2x and 4x resize works… but 4x really needs *a lot* of GPU memory…

didn’t push any of this yet, but will some time soon.

---

## #178 **** (@niklasiivari) · 2025-03-05 19:16

[@hanatos](/u/hanatos) would you have any idea what is going wrong here, trying to use vkdt filmsim, but pictures always look purple, and no amount of color or filter adjustment will fix it. Happening on two different computers too, both on OpenSUSE tumbleweed (tried AppImage and compiling) and Windows.

I have created the filmsim.lut as instructed on the GitHub page.

[[![Screenshot From 2025-03-05 21-07-27](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/a/0afa515fe66aaae1fe9ef8ccf00df3aca7fa3dcc_2_690x405.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/a/0afa515fe66aaae1fe9ef8ccf00df3aca7fa3dcc_2_690x405.png)

Screenshot From 2025-03-05 21-07-271943×1142 667 KB](/uploads/short-url/1z74QR87chRXzbc8MXgZtcwVEzW.png?dl=1)

---

## #179 **jo** (@hanatos) · 2025-03-06 09:12

> **@niklasiivari** (帖子 #178):
> trying to use vkdt filmsim, but pictures always look purple

…would you have a raw + cfg file for me to see if i can reproduce?

---

## #180 **** (@niklasiivari) · 2025-03-06 11:45

Here you go:

[_DSC0375.NEF.cfg](/uploads/short-url/fH7DLhCq3Ahd1Ljorjy36wz3iZa.cfg) (3.8 KB)

[_DSC0375.NEF](/uploads/short-url/ne3SC6ExYUAme4tqWFywZUFC7yc.NEF) (25.5 MB)

---

## #181 **Andrea** (@arctic) · 2025-03-06 12:23

> **@hanatos** (帖子 #177):
> out2244×1080 851 KB
out2244×1080 851 KB

This look actually quite promising! Considering the simplified model.

[![:grinning:](https://discuss.pixls.us/images/emoji/apple/grinning.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grinning.png?v=12)

I am a bit concerned by the whiter halos when you are pushing the inhibition, but it is probably completely overboard as you said.

I hope I got your approximations right. Here are a few comments.

> **@hanatos** (帖子 #177):
> does that make any sense to you at all? too much approximation?

I think that not saturating the amount of inhibition might violate the “conservation of mass”. I mean that in chemistry you can make as much products as the reagents can allow. If you finish reagents the reaction will stop. Since the inhibitors molecules are released when the main dyes (CMY) are produced in the emulsion, then when we reach density max it would make sense that also the inhibitors reaches a maximum. Or if no density is produced there should not be any effect of the inhibitors because they are not produced in the first place.

Using only M*e does not take into account this saturation. This might be too drastic in the region of the photos when density is saturated (before toe and past the shoulder) but still will hold fine in the linear part. So the question might be if we are fine with this approximation.

My modeling of the interlayer effects and dir couplers came also from studying some sketches from the Hunt’s book [Hunt, The reproduction of color, 6th ed, Wiley 2004]. At page 256, there is a sketch of how the interlayer effects should work on film.

[[![hunt_page_256](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/6/c6305fd335bbfdb7371b628c565ac6e4334e6ef1.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/6/c6305fd335bbfdb7371b628c565ac6e4334e6ef1.png)

hunt_page_256690×512 98.6 KB](/uploads/short-url/shgbcoyC1uQvI44RVoiXQpOcyKB.png?dl=1)

It is for positive film, but the concepts should hold. Let’s focus on panel(c), It shows a few experiments of test wedges in which the exposure of two channels (red and green, C and M layers) is kept constant while the blue exposure follows a ramp (Y layer). The final C and M density will be affected by the amount of density developed in the Y channel.

I made a small script to reproduce the experiment in panel(c) with your model and the current one in `agx-emulsion`.

Both models leaves unaffected density curves when a neutral ramp is used as exposure.

[[![Figure_1](https://d2x313g9lpht1q.cloudfront.net/original/3X/4/0/40ade0e80fd4694a31999c16f8029c3cb6173e2d.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/4/0/40ade0e80fd4694a31999c16f8029c3cb6173e2d.png)

Figure_1640×480 23.4 KB](/uploads/short-url/9eb5Er668S7abZjfOwsgGn2TNdX.png?dl=1)

[[![Figure_2](https://d2x313g9lpht1q.cloudfront.net/original/3X/2/a/2ac4d0d7f0144e493d0f4f9de82a7157b0a09f31.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/2/a/2ac4d0d7f0144e493d0f4f9de82a7157b0a09f31.png)

Figure_2640×480 24.1 KB](/uploads/short-url/66lJeNambVnbnYwgUPiKABNLxMl.png?dl=1)

When only blue light is exposed with a ramp and the other channel with constant exposure, these are the effects.

[[![Figure_3](https://d2x313g9lpht1q.cloudfront.net/original/3X/2/e/2e0d84f10bb4c5deac12f3baa0c607acd0cb138e.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/2/e/2e0d84f10bb4c5deac12f3baa0c607acd0cb138e.png)

Figure_3640×480 27.4 KB](/uploads/short-url/6zoVzAGQYMv9zZNAE1rzlIPPo5w.png?dl=1)

[[![Figure_4](https://d2x313g9lpht1q.cloudfront.net/original/3X/3/e/3e049d53794d155f2225e2d32bab378035f10824.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/3/e/3e049d53794d155f2225e2d32bab378035f10824.png)

Figure_4640×480 34.3 KB](/uploads/short-url/8QDumOxER0bTrlNOizNP5LTJI6o.png?dl=1)

<details>
<summary>
Code for making the plots</summary>

<pre data-code-wrap="python"><code class="lang-python">import numpy as np
import matplotlib.pyplot as plt

def curve(e, ks):
 y = np.zeros((3, e.shape[0]))
 for i, k in enumerate(ks):
 gamma = k[0]
 e0 = k[1]
 ymax = k[2]
 c1 = k[3]
 c2 = k[4]
 y[i] = ( gamma/c1 * np.log10(1 + 10**(c1 * (e - e0) ) )
 - gamma/c2 * np.log10(1 + 10**(c2 * (e - e0 - ymax/gamma)))
 )
 return y

k0 = [[ 0.6, -1.4, 2.00, 2, 1],
 [ 0.6, -1.5, 1.95, 2, 1],
 [ 0.6, -1.6, 2.05, 2, 1]]
k0 = np.array(k0)

N = 1024
e = np.linspace(-4,5,N) # log exposure
dc = curve(e, k0) # density curves

def plot_density(e, dc, ax=None, add_labels=True, alpha=1):
 if ax is None:
 _, ax = plt.subplots()
 # colors = ['tab:red', 'tab:green', 'tab:blue']
 colors = ['tab:cyan', 'tab:pink', 'gold']
 for i in np.arange(3):
 if add_labels==True:
 # l='RGB'[i]
 l='CMY'[i]
 else: l ='_nolegend_'
 ax.plot(e, dc[i], color=colors[i], label=l, alpha=alpha)
 ax.set_xlabel('Log Exposure')
 ax.set_ylabel('Density')
 ax.legend()

def interp_with_curves(x, e, dc):
 if np.size(e.shape) == 1:
 e = np.vstack((e,e,e))
 d = np.zeros((3, e.shape[1]))
 for i in np.arange(3):
 d[i] = np.interp(x[i], e[i], dc[i])
 return d

##############################################################################
# models

def density_dir_model_a(raw, e, dc, M):
 e = np.vstack((e,e,e)) # log exposure
 d_max = np.max(dc, axis=1)

 d_max = d_max[:,None]
 raw_mid = e - np.einsum('ck, cm->mk', dc/d_max, M)
 dc0 = interp_with_curves(e, raw_mid, dc) # density curves 0, before inhibition

 d0 = interp_with_curves(raw, e, dc)
 raw_corr = raw - np.einsum('ck, cm->mk', d0/d_max, M) # corrected log exposure

 d = interp_with_curves(raw_corr, e, dc0)
 return d

def density_dir_model_hanatos(raw, e, dc, M):
 M = M*0.1 # reduced inhibition matrix for matching roughly the models
 e = np.vstack((e,e,e)) # log exposure

 e_mid_corr = np.einsum('ck, cm->mk', e, np.linalg.inv(np.eye(3)-M))
 dc0 = interp_with_curves(e_mid_corr, e, dc) # density curves 0, before inhibition

 raw_corr = raw - np.einsum('ck, cm->mk', e, M) # corrected log exposure
 d = interp_with_curves(raw_corr, e, dc0)
 return d

##############################################################################
# test models
M = np.ones((3,3))/3

def test_models(e, dc, M, density_model, e_levels=[-1, 0, 1, 4], experiment='neutral_ramp'):
 _, ax = plt.subplots()
 alpha = [0.3,0.5,0.7,1]
 for i, ei in enumerate(e_levels):
 if experiment=='rg_constant':
 raw = np.vstack((ei*np.ones(N), ei*np.ones(N), e))
 elif experiment=='g_constant':
 raw = np.vstack((e, ei*np.ones(N), e))
 elif experiment=='neutral_ramp':
 raw = np.vstack((e, e, e))
 d = density_model(raw, e, dc, M)
 plot_density(e, d, ax=ax, add_labels=False, alpha=alpha[i])

# neutral ramp
test_models(e, dc, M, density_dir_model_hanatos, experiment='neutral_ramp')
plt.title('hanatos DIR Couplers Model - Neutral Ramp')

test_models(e, dc, M, density_dir_model_a, experiment='neutral_ramp')
plt.title('Current agx-emulsion DIR Couplers Model - Neutral Ramp')

# hunts panel(c) experiment pag 256
test_models(e, dc, M, density_dir_model_hanatos, experiment='rg_constant')
plt.title('hanatos DIR Couplers Model')

test_models(e, dc, M, density_dir_model_a, experiment='rg_constant')
plt.title('Current agx-emulsion DIR Couplers Model')
plt.show()
</code></pre>

</details>

Tell me in case my implementation in the python code does not correspond with what you meant.

I think what is happening below log exposure = 2 (or above log exposure = 2.5) is not realistic in the sense that the Y layer cannot release inhibitors and should not affect C and M (or exhausted all the amount of inhibitors it could release on the other side). So densities of C and M dyes should not change anymore before the toe (or after the shoulder) because the Y layer is not affected anymore by the reduced (or added exposure).

Also I think that if the layers C and M can produce inhibitors they should also affect layer Y. The higher the density on C and M and the more inhibited the Y layer should be (This is not really shown in Hunt’s sketch, probably because he aligned the yellow curves to make a clearer sketch).

In my opinion, in this physically based simulations, reproducing what makes sense from a physical point of view really helps in the final look. But of course, we can take choices that helps with computational efficiency or convenience. This violate the chemical nature of the process a bit too much I think.

[![:grin:](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)

 What’s your take?

---

## #182 **jo** (@hanatos) · 2025-03-06 13:01

> **@niklasiivari** (帖子 #180):
> Here you go:

hmm works for me. here’s my lut, maybe something went wrong while generating it:

[filmsim.lut](/uploads/short-url/upRe0PddpftEQAUZLq6fsYy8II6.lut) (144.0 KB)

---

## #183 **** (@niklasiivari) · 2025-03-06 13:07

Thank you, works perfectly now!

Was this created using the same script available in the repo? I guess I might be missing some required python libs, but I did not see any errors in the output when running, and I tried running it both in venv with the agx dependencies and using system packages, so idk.

---

## #184 **jo** (@hanatos) · 2025-03-06 13:10

yeah we will never find out

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 i should package and ship this thing. always hesitant checking in generated files into git, but the convenience gain in this case is considerable…

---

## #185 **jo** (@hanatos) · 2025-03-06 13:19

> **@arctic** (帖子 #181):
> violate the “conservation of mass

right. i would like to conserve energy. thanks for finding all these extra plots! will think about how to refine the code so it doesn’t slow down…

---

## #186 **Bob** (@PhotoPhysicsGuy) · 2025-03-06 15:41

> **@hanatos** (帖子 #185):
> i would like to conserve energy.

Which energy do you want to be conserved though?

The simulated process converts photon energy from the light field (or a flux of photons) of the scene into “breaking” predeposited silver-halides to form silver, sensitized to different wavelengths in different layers.

From then on it’s mass ratios in chemical reactions. At least I think that DIR-couplers are not photosensitive themselves. (EDIT: by all means, I could have gotten this wrong)

I think that also means: one can totally “upconvert” IR-exposure to modulate visible light (Kodak Aerochrome) or “downconvert” x-ray exposure to modulate visible light (your typical analog x-ray).

The sensitizers in color-negative can be sensitive to a different wavelengths of light than the formed dyes let pass through in the positive.

I think that breaks energy conservation in my understanding of the term.

---

## #187 **jo** (@hanatos) · 2025-03-06 15:43

mass is energy is all i was saying. in my field we usually keep matter/stuff you can touch as it is, so my number one concern is usually conservation of energy, which is the same thing.

---

## #188 **Andrea** (@arctic) · 2025-03-06 17:14

In the end Einstein showed the relationship of mass and energy <span class="math">E=mc^2</span>, so we can definely reinterpret Lavoisier’s law of conservation of mass in terms of energy

[![:grin:](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)

---

## #189 **jo** (@hanatos) · 2025-03-06 17:18

> **@niklasiivari** (帖子 #183):
> Was this created using the same script available in the repo? I guess I might be missing some required python libs, but I did not see any errors in the output when running, and I tried running it both in venv with the agx dependencies and using system packages, so idk.

i can confirm that newly created luts turn purple. after a git bisect in the agx-emulsion repo, i find that this: 0cdb191086811c73de0d06b42124591397a49ac8 is the first bad commit. will have to see what’s going on. it did replace all the profile json files, but it’s likely that just my python conversion doesn’t understand it right. i believe it switched from 10nm spacing to 5nm in the data, and my python is just a bit assumption-happy

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 i’m sure i can fix it.

---

## #190 **Nate Weatherly** (@NateWeatherly) · 2025-03-06 19:04

[@arctic](/u/arctic) Could you give a bit more info about the compensation removal factor/density/transition? Is this meant to lower the blacks in the “print” to visually compensate for the relatively deeper blacks on a display vs a print, like the EOTF in the davinci resolve color transform node (which is the difference between the REC709 encoding TF and the Gamma 2.4 display TF)?

I’ve been trying to play with it, but no matter what values I use I can’t see any difference in the output. I made sure that it’s active and the glare percent is set at zero. Tried with computing the full image and it’s still the same. Am I missing something?

Also, just curious why the Kodak Endura Premier print paper is so much more contrasty than the other papers. I noticed that the Porta 400 data sheet specifies that the film is designed to be printed on Endura Premier, but the result is far more contrasty than my Portra 400 scans and even more so once you adjust the black/white points like in a scan. Does it have something to do with Endura Premier being designed for digital rather than optical printing? Thanks!

---

## #191 **** (@mikae1) · 2025-03-06 20:15

I’ve got `vkdt-rawler-pentablet-0.9.99-353-g8c9e66c4-x86_64.AppImage` running [@hanatos](/u/hanatos). Can I find an agx-emulsion module in it? Have tried searching for “emulsion”, “agx” and “film” using “filter module by name” but I’m not finding it.

---

## #192 **** (@mikae1) · 2025-03-06 20:47

> **@arctic** (帖子 #173):
> Indeed as you predicted the effect was not very visible.

Thanks. Was flipping between the two and was just about to write: TBH, there isn’t much of a difference to my eyes.

[![:smiley:](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)

> **@arctic** (帖子 #176):
> I guess that the physical interaction of film and print paper during the analog printing process is what we would like to preserve, because it is what encodes part of the look. It definitely encodes color shifts and style, just compare Portra and Endura Premier for example.

As I said earlier, I guess it all boils down to what we want to simulate. Early 2010 VSCO presets and profiles for Lightroom and Adobe Camera Raw tried as best as they could to simulate Noritsu and Frontier scanner interpretations for a wide range of films. They obviously hadn’t come up with the splendid idea of using the technical documents.

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

> **@arctic** (帖子 #176):
> When looking at simulated images on screens we should probably emulate all paper characteristics.

For a medium (negative film) that was meant for printing I think it makes more sense to simulate the paper output. But still, for the paper copy to be usable in the digital realm, we would have had to scan it. If we want to emulate the entire chain I think it’d be the following:

1. (C-41) film development
2. (RA-4) paper development
3. scanning

The scan step could be represented by black and white points and possibly a curve control together with a histogram. If agx-emulsion is implemented in vkdt or darktable we could just put levels and curves modules after the new and shiny emulsion tone mapper module.

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

For the black and white point controls to be truly usable in agx-emulsion a histogram would have to be there though.

---

## #193 **Andrea** (@arctic) · 2025-03-07 00:14

> **@NateWeatherly** (帖子 #190):
> Could you give a bit more info about the compensation removal factor/density/transition? Is this meant to lower the blacks in the “print” to visually compensate for the relatively deeper blacks on a display vs a print, like the EOTF in the davinci resolve color transform node (which is the difference between the REC709 encoding TF and the Gamma 2.4 display TF)?

Print paper reflects some of the incoming light, creating glare. This effectively brightens the shadows. Print paper is also designed to counteract viewing glare by making shadows deeper than expected, encoding this in the density curves.

`agx-emulsion` has random glare simulation that should compensate for this, adding also some noise in the blackest parts of the print.

As discussed with [@mikae1](/u/mikae1), for printing maybe we don’t want to add random glare that will be already present in the final real paper. So in this case the viewing glare compensation removal can brighten a bit the shadows by slightly changing the density curves of the paper.

Here is an example of how it works with `transition`=0.3 and `density`=1.2.

`density` defines the density at witch the compensation kicks in.

`transition` defines the width (in density values) of the transition from the unaffected region to the compensated region.

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/2/7/27d0aeac84726ada3aed964f4db04c2a708f3d1e.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/2/7/27d0aeac84726ada3aed964f4db04c2a708f3d1e.png)

image857×480 49.4 KB](/uploads/short-url/5GdII7E206MfdwzXnuqc2BClGEK.png?dl=1)

> **@NateWeatherly** (帖子 #190):
> I’ve been trying to play with it, but no matter what values I use I can’t see any difference in the output. I made sure that it’s active and the glare percent is set at zero. Tried with computing the full image and it’s still the same. Am I missing something?

You noticed a bug! Thanks! The compensation was actually not happening. I just pushed to the `main` branch a fix that enables the viewing glare compensation removal. Test it again if you have time.

> **@NateWeatherly** (帖子 #190):
> Also, just curious why the Kodak Endura Premier print paper is so much more contrasty than the other papers.

I think that it is very contrasty because it is a consumer paper, intended to give some wow effect for the average consumer (a bit like bass and high boost in headphones). But I am not an expert of the real paper, since I have never used actual RA-4 paper.

> **@NateWeatherly** (帖子 #190):
> but the result is far more contrasty than my Portra 400 scans and even more so once you adjust the black/white points like in a scan.

Negatives have huge latitude and in a scan we can actually preserve a lot of it and easily generate lower contrast images. RA-4 print paper is optimized to give pleasant and satisfactory contrast. According to my moderate experience it is more contrasty that you would expect when compared to generic negative scans. But there might be people more expert than me that could comment and have a better view of this.

In the end the simulation does what the data encodes, so if we trust the data (and the monkey digitizing them) this is the contrast that the paper should have.

---

## #194 **Andrea** (@arctic) · 2025-03-07 00:15

look for `filmsim`!

[![:wink:](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)

---

## #195 **Andrea** (@arctic) · 2025-03-07 00:27

> **@mikae1** (帖子 #192):
> (C-41) film development
(RA-4) paper development
scanning

Right now the scanning step is more of a simulation of the human vision looking at the print. That is probably even better than wanting to simulate a scanner in my opinion.

> **@mikae1** (帖子 #192):
> The scan step could be represented by black and white points and possibly a curve control together with a histogram. If agx-emulsion is implemented in vkdt or darktable we could just put levels and curves modules after the new and shiny emulsion tone mapper module.

Indeed! But we can probably have a switch that does “analytic” black-white point correction, making white truly white, and black truly black. For the white there is already `special` >> `print_density_min_factor`, that when set to 0 removes absorption of the base of the paper, making white [1,1,1] if present in the print. Since we know the maximum density of the paper (usually approx. 2.5/3) we can also guess the black point and have an automatic correction to make black [0,0,0]. I will give a though of how to do this neatly!

---

## #196 **** (@mikae1) · 2025-03-07 08:22

> **@arctic** (帖子 #195):
> Right now the scanning step is more of a simulation of the human vision looking at the print. That is probably even better than wanting to simulate a scanner in my opinion.

Sorry for the confusion. I **wasn’t** trying to say that the point of step 3 was to simulate the characteristics of the scanner (à la VSCOs Noritsu/Frontier attempts), but rather to assume a *perfect* digitization with some ability to tweak black and white points and a curve so (that the exported file can be sent for print).

Perhaps this becomes more philosophical than technical, but what we do when we export the picture (or “Save Selected Layers”) from agx-emulsion is the equivalent of scanning the print. My thought was that it could make sense to give the user basic control over this “scan”.

> **@arctic** (帖子 #193):
> Print paper reflects some of the incoming light, creating glare. This effectively brightens the shadows. Print paper is also designed to counteract viewing glare by making shadows deeper than expected, encoding this in the density curves.
agx-emulsion has random glare simulation that should compensate for this, adding also some noise in the blackest parts of the print.
As discussed with @mikae1, for printing maybe we don’t want to add random glare that will be already present in the final real paper. So in this case the viewing glare compensation removal can brighten a bit the shadows by slightly changing the density curves of the paper.

Thanks for reiterating. I realize now how fantastic this sounds and perhaps it would be enough for your app. I’ll download and give it a try. There’s always GIMP to do further “post scan” corrections.

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 When agx-emulsion gets implemented in other apps (like vkdt or darktable), levels and curves can be applied via modules placed post agx-emulsion if necessary.

Speaking of darktable. How difficult would it be to port GLSL code C for module use in darktable? Perhaps a question for [@hanatos](/u/hanatos), [@flannelhead](/u/flannelhead) or [@Pascal_Obry](/u/pascal_obry)?

> **@arctic** (帖子 #194):
> look for filmsim!

Dang, no results!

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/8/c81c79db825c3af28f14ca0c18ebbcc6d31705d8.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/8/c81c79db825c3af28f14ca0c18ebbcc6d31705d8.jpeg)

image374×577 80.6 KB](/uploads/short-url/sygve2342U1mEerWQaHooPoRYLe.jpeg?dl=1)

---

## #197 **jo** (@hanatos) · 2025-03-07 09:01

> **@mikae1** (帖子 #196):
> Dang, no results!

[[![2025-03-07-095945_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/9/398b92ba2b04b9e28967e46bb3f2469c013ae68d_2_690x454.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/9/398b92ba2b04b9e28967e46bb3f2469c013ae68d_2_690x454.png)

2025-03-07-095945_hyprshot1335×879 303 KB](/uploads/short-url/8d4fuGgqNL3bmzkEJfxmVYCOqrb.png?dl=1)

has to be int this^ dialog, i.e. apply preset or press hotkey ctrl-p.

also, if you pull vkdt now ships with good 5nm spaced filmsim.lut. this means everybody has to please delete their `~/.config/vkdt/data/filmsim.lut` because the stuff in the home directory would take precedence (and likely be the old lut).

---

## #198 **** (@mikae1) · 2025-03-07 10:22

> **@mikae1** (帖子 #196):
> what we do when we export the picture (or “Save Selected Layers”) from agx-emulsion is the equivalent of scanning the print.

I’m certainly thinking way ahead of the development, but this could actually be made a fun design quirk. The “compute full image” checkbox could be removed and “Run” could be replaced with “Preview” and “Scan” buttons. The compute time would suddenly make sense.

[![:wink:](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)

Epson Scan calls it Preview and Scan:

[[![epson_scan_scan](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/a/5a17a05b3def2eb8957272c8067e8ee0c5a53252_2_690x631.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/a/5a17a05b3def2eb8957272c8067e8ee0c5a53252_2_690x631.png)

epson_scan_scan837×766 123 KB](/uploads/short-url/cQZAGjjK6xMvAN7DUtKLLCidAHw.png?dl=1)

VueScan calls it Preview and Scan too:

[[![vuescan_scan](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/5/05120cf2832e9dbf10ac20b2ce7ff63ce531cd4e_2_521x1000.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/5/05120cf2832e9dbf10ac20b2ce7ff63ce531cd4e_2_521x1000.png)

vuescan_scan668×1280 107 KB](/uploads/short-url/IR3KGpUDrGHdbkJ18txT4NREqW.png?dl=1)

“Save” would either save the preview or the full image (depending on how it was last rendered).

---

## #199 **Andrea** (@arctic) · 2025-03-08 07:36

> **@mikae1** (帖子 #198):
> Epson Scan calls it Preview and Scan:

That’s a very good suggestion, especially because this a UI optimized for slow “processing”, like negative scans with a flat bed scanner. And it somewhat adapt well with the slow processing of `agx-emulsion`

[![:grin:](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)

, that requires a preview to be usable. Also the crop controls are very similar.

Thank you for the suggestion. I had a quick look to `magicgui` capabilities. This library is super nice for making extremely quick and clean code GUIs, but it might suffer of generality. I had found a solution for adding multiple buttons but ruins alignment of the other widgets. I will spend some more effort on it. Also working on a simple sidecar file for the settings, that will be useful for tracking some tests when I am comparing things.

---

## #200 **jo** (@hanatos) · 2025-03-08 17:02

looking at my code i think i guess the python would look like

```
def density_dir_model_hanatos(raw, e, dc, M):
 M = M*0.1 # reduced inhibition matrix for matching roughly the models
 e = np.vstack((e,e,e)) # log exposure

 # compute couplers:
 c = np.einsum('ck, cm->mk', raw, M)
 # apply couplers to raw exposure:
 raw = raw - c;
 # now apply our fake D_0(.) which is assuming monochromatic (so we make it mono and apply it 3x)
 e_corr = np.zeros_like(raw)
 e_corr[0,:] = np.einsum('ck, cm->mk', np.vstack((raw[0,:],raw[0,:],raw[0,:])), np.linalg.inv(np.eye(3)-M))[0,:]
 e_corr[1,:] = np.einsum('ck, cm->mk', np.vstack((raw[1,:],raw[1,:],raw[1,:])), np.linalg.inv(np.eye(3)-M))[1,:]
 e_corr[2,:] = np.einsum('ck, cm->mk', np.vstack((raw[2,:],raw[2,:],raw[2,:])), np.linalg.inv(np.eye(3)-M))[2,:]
 # now the only time we evaluate the D lut:
 d = interp_with_curves(e_corr, e, dc)
 return d

```

which is not really better than your plot:

[[![20250308_17h58m10s_grim](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/f/bfb6d0d09528db86b23ce777d4a5069526692cab_2_690x303.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/f/bfb6d0d09528db86b23ce777d4a5069526692cab_2_690x303.png)

20250308_17h58m10s_grim2419×1065 190 KB](/uploads/short-url/rlYSpGt6DG8lOFHm59KASdCd2wb.png?dl=1)

the idea is that i only have to call the density lut *once* and can do the rest analytically. also it bugs me that we can’t reverse the measured density curves to “actual” curves that would physically happen in the film before couplers. i tried to run some fixed point iteration as an offline preprocess but the results looked horrible. i might have a bug because my python is abysmal, but also it might just not work like this. results match the uncontrolled colour shifts you described earlier when not respecting the density curves as data.

---

## #201 **Jonathan Bieler** (@jonathanBieler) · 2025-03-08 17:33

I uploaded the same shot taken with film & digital here for testing : [Tree above stream : digital & film](https://discuss.pixls.us/t/tree-above-stream-digital-film/48707)

I was trying to compare the digital converted with agx-emulsion with the film but I struggled to get close, although I might have messed up something.

---

## #202 **nosle** (@nosle) · 2025-03-08 20:50

> **@nosle** (帖子 #138):
> Does anyone know how different the nc portras were to the newer prefix less versions?

Answering myself here. Did some quick searching and some seem to suggest that the suffix less portras are somehow inbetween the NC and VC portras of old. Specifically it’s suggested that 160 is most like 160 NC and 400 pulls toward VC and 800 most like VC.

Now the reason for my question in the first place is that I found the agx simulation to produce more vivid and “distorted” images than my film samples. With this info about the new portras it makes sense as the 400 should be more vivid and contrasty than the NC.

Recently I’ve only shot the 160 portra which is close to what I remember the 160 NC being like.

So now we need the 160 simulation for those more earthy lower contrast tones. My agx simulations are looking quite “spiky”

---

## #203 **** (@mikae1) · 2025-03-08 21:42

> **@arctic** (帖子 #199):
> especially because this a UI optimized for slow “processing”, like negative scans with a flat bed scanner. And it somewhat adapt well with the slow processing of agx-emulsion , that requires a preview to be usable.

Yeah, that was my thinking. Bonus points for making “the scan” grow vertically ([7m19s](https://www.youtube.com/watch?v=MYC1xii3HmM#t=7m19s)) as the image is processed.

[![:wink:](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)

> **@arctic** (帖子 #199):
> Also working on a simple sidecar file for the settings, that will be useful for tracking some tests when I am comparing things.

That’s wonderful! I’ve resorted to screenshot for documenting settings. Another alternative would be to embed settings as XMP metadata (like Adobe does).

> **@jonathanBieler** (帖子 #201):
> I was trying to compare the digital converted with agx-emulsion with the film but I struggled to get close, although I might have messed up something.

Considering how far from a usable image a color negative is, there’s more than a million ways to interpret a negative if you digitize it. It was meant to be printed on paper using a color enlarger. That’s the process agx-emulsion attempts to simulate.

---

## #204 **Andrea** (@arctic) · 2025-03-09 14:03

> **@hanatos** (帖子 #200):
> 20250308_17h58m10s_grim2419×1065 190 KB
20250308_17h58m10s_grim2419×1065 190 KB

Ok, that makes more sense and looks better for the yellow layer!

> **@hanatos** (帖子 #200):
> also it bugs me that we can’t reverse the measured density curves to “actual” curves that would physically happen in the film before couplers.

It bugs me too actually.

[![:smile:](https://discuss.pixls.us/images/emoji/apple/smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smile.png?v=12)

 When thinking about the solution for this part of the modeling, it felt a bit dirty to rely on the double LUT interpolation of the density. However, this gave the best results and sounded more grounded to the chemical nature of the process.

---

## #205 **Andrea** (@arctic) · 2025-03-09 19:58

> **@nosle** (帖子 #202):
> Answering myself here. Did some quick searching and some seem to suggest that the suffix less portras are somehow inbetween the NC and VC portras of old. Specifically it’s suggested that 160 is most like 160 NC and 400 pulls toward VC and 800 most like VC.

I found this [file](https://125px.com/docs/film/kodak/PORTRA_Film_Q&A.pdf) from Kodak on 125px database, with some Q&A about Portra.

They say: "PORTRA 160NC and PORTRA 400NC Films have the same contrast and colour saturation as the previous generation. The contrast of the new PORTRA 160VC and PORTRA 400VC Films has been lowered and the colour saturation has been increased (via interlayer interimage effects). "

They suggest that the difference is based on “interlayer interimage effects” referring to the ratio of normal coloured couplers and DIR couplers in the emulsion.

> **@nosle** (帖子 #202):
> So now we need the 160 simulation for those more earthy lower contrast tones. My agx simulations are looking quite “spiky”

I will definitely add Portra 160 and 800 in the future. On the current Portra 400 sim you could try to reduce the amount of DIR couplers (their amount is just guessed right now, and according to your perception might be to high and this is good feedback, use `dir couplers amount`), and you can also reduce the gamma of the print paper via `print gamma factor` for tuning contrast (also affects saturation).

Here is an example using Kodak Portra and Endura Premier. This is the current default output:

[[![portra_400_endura_premier](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/3/d34c9f1c1136f212c4440b6fffc037a3294b2e61_2_666x1000.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/3/d34c9f1c1136f212c4440b6fffc037a3294b2e61_2_666x1000.jpeg)

portra_400_endura_premier2000×3000 678 KB](/uploads/short-url/u9eUeXKWulTPw45kNbJ9zrdLVGp.jpeg?dl=1)

(left) couplers reduced to 0.7, (right) couplers reduced to 0.5

[[![portra_400_endura_premier_07cpl](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/c/7c2aea3ede3fdee090f4805fee59d9f35edd6068_2_330x480.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/c/7c2aea3ede3fdee090f4805fee59d9f35edd6068_2_330x480.jpeg)

portra_400_endura_premier_07cpl2000×3000 671 KB](/uploads/short-url/hIr9nLWMiQAFKKzCYdXYesVifK8.jpeg?dl=1)

[[![simulation result_05cpl](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/5/6528410ffd14391c20175994736fa5b19cbbd7f7_2_330x480.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/5/6528410ffd14391c20175994736fa5b19cbbd7f7_2_330x480.jpeg)

simulation result_05cpl2000×3000 667 KB](/uploads/short-url/eqSt3qHWlokNi6sMBYGv3OqodbV.jpeg?dl=1)

(left) couplers 0.5 and print gamma factor 0.9, (right) couplers 0.5 and print gamma factor 0.75

[[![portra_400_endura_premier_05cpl_09gamma](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/7/276bb640876dab22a8db8b22b3e2cfdd046baf3b_2_330x480.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/7/276bb640876dab22a8db8b22b3e2cfdd046baf3b_2_330x480.jpeg)

portra_400_endura_premier_05cpl_09gamma2000×3000 640 KB](/uploads/short-url/5CJomZ6E5iGe1tnUjMlEmXaH6UH.jpeg?dl=1)

[[![portra_400_endura_premier_05cpl_075gamma](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/0/30ad70d3c81c413195b6c49b30e77d4a9c1bfc21_2_330x480.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/0/30ad70d3c81c413195b6c49b30e77d4a9c1bfc21_2_330x480.jpeg)

portra_400_endura_premier_05cpl_075gamma2000×3000 588 KB](/uploads/short-url/6WCvQpCzYYLMUbHp8GYar81kumB.jpeg?dl=1)

And this is an intermediate “unspiked” version with couplers 0.7 and print gamma factor 0.9.

[[![simulation result_07cpl_09gamma](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/c/4c5c1ce7347a0cb19c83468bc4dc656cd921be6c_2_666x1000.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/c/4c5c1ce7347a0cb19c83468bc4dc656cd921be6c_2_666x1000.jpeg)

simulation result_07cpl_09gamma2000×3000 645 KB](/uploads/short-url/aTvDBjfK1kWImd3yTnfwp9aFGu8.jpeg?dl=1)

---

## #206 **nosle** (@nosle) · 2025-03-09 20:06

Thanks for the further info on those sliders. I will experiment! I think I was to meak with the couplers slider in my previous tests.

Regarding that Kodak pdf though, it seems to be from 2006 and that’s before the suffix drop tweak. The non suffixed Portra 160 was released in 2011. The pdf is interesting even if its about earlier run of tunings of the film.

---

## #207 **Andrea** (@arctic) · 2025-03-09 20:07

> **@jonathanBieler** (帖子 #201):
> I was trying to compare the digital converted with agx-emulsion with the film but I struggled to get close, although I might have messed up something.

I completely agree with the comment of [@mikae1](/u/mikae1), that when you digitize the negative the way you interpret them can drastically change the output, and choices needs to be taken. Therefore comparisons and “output matching” are not given or straightforward.

The negative is designed to capture as much as possible of the scene and to produce and intermediate image that needs to be interpreted, and it is by definition low gamma (and contrast).

---

## #208 **nosle** (@nosle) · 2025-03-09 20:32

> **@jonathanBieler** (帖子 #201):
> I was trying to compare the digital converted with agx-emulsion with the film but I struggled to get close, although I might have messed up something.

What process did you use? Did you save the agx “negative” and developed it next to the film “scan” in dt?

Agx output normally has the printing process built in right? Which should means the characteristics of the paper play into it as well. Your photographed negative can’t simulate that part of the process?

---

## #209 **** (@commutergraphics) · 2025-03-09 20:59

some really beautiful examples here

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

---

## #210 **** (@mikae1) · 2025-03-10 18:44

> **@arctic** (帖子 #205):
> you can also reduce the gamma of the print paper via print gamma factor for tuning contrast (also affects saturation).

Oh, helpful! Had completely overlooked this. Should gamma 1 be the “right” amount as per the tech sheets? Speaking of all these settings. Is there a way to save the settings as a default? My settings seem to disappear when closing and opening napari.

---

## #211 **Andrea** (@arctic) · 2025-03-11 21:49

> **@mikae1** (帖子 #210):
> Should gamma 1 be the “right” amount as per the tech sheets

Exactly, when `print gamma factor`=1 the density curves of the paper are the ones on the datasheet. Factors higher or lower than 1 stretch the density curves accordingly. The effective gamma of the paper is “original gamma x `print gamma factor`”.

> **@mikae1** (帖子 #210):
> Is there a way to save the settings as a default? My settings seem to disappear when closing and opening napari.

Unfortunately, the defaults settings are hardcoded in the gui file for now (easiest and quickest implementation). So there is no easy way to save a presets or new defaults at the moment. Of course you can manually change the python gui file, but it is not a very good solution for future updates. When I will implement the loading of the settings files, it will be possible, though.

---

## #212 **** (@mikae1) · 2025-03-11 22:04

> **@arctic** (帖子 #211):
> Exactly, when print gamma factor=1 the density curves of the paper are the ones on the datasheet.

> **@arctic** (帖子 #211):
> Unfortunately, the defaults settings are hardcoded in the gui file for now (easiest and quickest implementation).

Thanks for confirming!

Does the negative size settings change the grain scale in any way? I’ve been thinking about how I enjoyed Alien Skin Exposure’s way of handling grain scaling.

[[![aseg](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/8/c807354cd2f0df15a6a7f654369bc1b4c36cd164.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/8/c807354cd2f0df15a6a7f654369bc1b4c36cd164.jpeg)

aseg682×578 76.5 KB](/uploads/short-url/sxwW872ktW35KnUYgT7Lxcwr0sQ.jpeg?dl=1)

It was possible to set film format and the grain size was automatically correctly scaled. The default grain size in agx-emulsion seems a bit small with my 24 MP files at default settings. I’ve been scaling up. “Seems small” is based on my experience from 15 years ago when I used to scan negatives every (work)day. So, I could very well be misjudging.

[![:smiley:](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)

---

## #213 **Andrea** (@arctic) · 2025-03-11 22:14

I explored solutions to have color print film working, and I discovered a little detail that I overlooked. Usually lighthouses in enlargers and cine print heads have heat absorbing filters that effectively block light in the NIR and above. This is done to not deposit to much heat on the negatives, that is produced by light sources like tungsten-halogen or carbon arc bulbs.

From a quick search, heat absorbing glass from Schott is an example of these kind of filters. And especially “KG 3” would be a typical filter found in cine print heads.

[[![COLOR-FILT-XMIT-9-800w](https://d2x313g9lpht1q.cloudfront.net/original/3X/4/9/499f1adca5895299d6e7cce86a4f825a16013a82.gif)](https://d2x313g9lpht1q.cloudfront.net/original/3X/4/9/499f1adca5895299d6e7cce86a4f825a16013a82.gif)

COLOR-FILT-XMIT-9-800w709×600 30.7 KB](/uploads/short-url/avhJDuSfF7jmpZzkrlUZFWsUR0K.gif?dl=1)

[from [Newport](https://www.newport.com/f/heat-absorbing-glass-filters)]

Adding this filter to the color enlarger magically fixed the fitting of neutral YMC filters for all the film stocks when printed on Kodak 2393 print film.

I also re-optimized Kodak Vision3 50D using Kodak 2393 as the reference printing medium instead of Kodak Portra Endura as I did for all the other photography film stocks.

Here is an example with this new additions added to the `main` branch:

darktable default edit: sigmoid (contrast=2), and everything else same as the input image to agx-emulsion

[[![Signature Edits Free RawsIMG_5824](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/a/6a8b0ffbc29d14a64dd91b8cf9913d5519cebb6d_2_330x480.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/a/6a8b0ffbc29d14a64dd91b8cf9913d5519cebb6d_2_330x480.jpeg)

Signature Edits Free RawsIMG_58241332×1999 529 KB](/uploads/short-url/fcwycY8gJEu5Tx8uP80ckBX3ViR.jpeg?dl=1)

(left) kodak vision3 50d on kodak 2393, (right) on kodak supra endura

[[![kodak_vision3_50d_kodak_2393_default_09pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/e/1ecb435c29c02b5d77ba9dd887c605c7cbb8f886_2_330x480.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/e/1ecb435c29c02b5d77ba9dd887c605c7cbb8f886_2_330x480.png)

kodak_vision3_50d_kodak_2393_default_09pe1998×3000 9.84 MB](/uploads/short-url/4opOqwbf4uFEXVYu21YqCFLLJ42.png?dl=1)

[[![kodak_vision3_50d_kodak_supra_endura_default_09pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/8/d8563f0c780638ccc25ad9491d73e6a8be2837cb_2_330x480.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/8/d8563f0c780638ccc25ad9491d73e6a8be2837cb_2_330x480.png)

kodak_vision3_50d_kodak_supra_endura_default_09pe1998×3000 9.68 MB](/uploads/short-url/uRNUKUbRHxTbrTi2hVtn2SPR1Jp.png?dl=1)

(left) kodak gold 200 on kodak 2393, (right) on kodak supra endura

[[![kodak_gold_200_kodak_2393_default_09pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/e/7ea4f66247ddaed84091ba7b5209fcc3fd8eecf8_2_330x480.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/e/7ea4f66247ddaed84091ba7b5209fcc3fd8eecf8_2_330x480.png)

kodak_gold_200_kodak_2393_default_09pe1998×3000 10.1 MB](/uploads/short-url/i4lAGn5x5TP2fw5Z14G4WeOeTnq.png?dl=1)

[[![kodak_gold_200_kodak_supra_endura_default_09pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/f/8ff30c3b17f6c6cfa20bebe18758c30900dd101a_2_330x480.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/f/8ff30c3b17f6c6cfa20bebe18758c30900dd101a_2_330x480.png)

kodak_gold_200_kodak_supra_endura_default_09pe1998×3000 9.96 MB](/uploads/short-url/kxr0m2CJLZdmiiPkIqh0ZlXL64O.png?dl=1)

Kodak Vision3 50D printed on Kodak 2393 has very neutral colors. The closest to a straight edit from darktable. Moreover, regular photography film, such as Kodak Gold 200, from these example looks a little more neutral when printed on cine print film Kodak 2393.

---

## #214 **Andrea** (@arctic) · 2025-03-11 22:29

> **@mikae1** (帖子 #212):
> Does the negative size settings change the grain scale in any way? I’ve been thinking about how I enjoyed Alien Skin Exposure’s way of handling grain scaling.

The negative size affects the statistics of the grain. Smaller negatives will be more grainy. It affects also the size of the dye clouds at extreme magnifications.

I believe that at normal magnifications (normal scans), the size of the grain is mainly affected by the resolution of the scanning/printing device. You can use `grain blur` and `scan lens blur`, both in pixel to fine tune this. I usually do not touch `scan lens blur`, though.

On 20-ish MP files I am pretty satisfied with `grain blur` = 0.85-0.95. Give it a try.

It could be automatized, but I found that I needed precise control on the ultimate spatial “unit of the image”. Anyways, the bulk of the appearance is done by the stochastic particle model that reacts fully to the negative size.

> **@mikae1** (帖子 #212):
> from 15 years ago when I used to scan negatives every (work)day

That sounds like a lot of experience

[![:blush:](https://discuss.pixls.us/images/emoji/apple/blush.png?v=12)](https://discuss.pixls.us/images/emoji/apple/blush.png?v=12)

! So you are definitely the most expert on this!

---

## #215 **Sébastien Guyader** (@sguyader) · 2025-03-11 23:27

For video color grading, colorists often use the Kodak 2383 instead of the 2393. Apparently the [2393 has deeper](https://cinematography.com/index.php?/forums/topic/101086-color-density-and-dynamic-range-of-kodak-vision-2383/) blacks, but the 2383 seems to be chosen most of the time by color grading gurus such as [Cullen Kelly](https://www.youtube.com/watch?v=ar-KL3X0Pcw).

---

## #216 **Andrea** (@arctic) · 2025-03-11 23:35

Thanks for the comment and links, I will digitize also data from 2383 and compare.

[![:+1:](https://discuss.pixls.us/images/emoji/apple/+1.png?v=12)](https://discuss.pixls.us/images/emoji/apple/+1.png?v=12)

---

## #217 **Tim Wood** (@streetfighter) · 2025-03-12 04:43

This software produces beautiful outputs and the whole idea of it is very fun in my opinion. Would love to see this as a module in darktable!

[@arctic](/u/arctic) have you considered adding the logic as a module in darktable as opposed to packaging it as a separate tool?

---

## #218 **** (@mikae1) · 2025-03-12 04:49

> **@streetfighter** (帖子 #217):
> @arctic have you considered adding the logic as a module in darktable as opposed to packaging it as a separate tool?

It’s written in Python and darktable in C, so it isn’t that easy. [@hanatos](/u/hanatos) has ported it to GLSL for vkdt. In [this](https://discuss.pixls.us/t/spectral-film-simulations-from-scratch/48209/196) post I asked some darktable devs how hard it would be porting to darktable, but I haven’t seen a reply.

> **@streetfighter** (帖子 #217):
> This software produces beautiful outputs

I truly agree! I’ve been using it quite a lot now and the basics are beginning to become more intuitive to me. Haven’t delved into all the options though.

[![:smile:](https://discuss.pixls.us/images/emoji/apple/smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smile.png?v=12)

---

## #219 **jo** (@hanatos) · 2025-03-12 08:36

> **@mikae1** (帖子 #218):
> @hanatos has ported it to GLSL for vkdt.

i think i’m nearing feature completeness with this. [here is the module documentation draft](https://jo.dreggn.org/vkdt/src/pipe/modules/filmsim/readme.html), including some explanations from [@arctic](/u/arctic)’s OP. so far it doesn’t have halation yet, but couplers and can resize up to 4x (if your GPU can). i’ll probably work on performance improvements / better spectral integration / maybe experiment with slightly better or faster grain and coupler implementation.

> **@mikae1** (帖子 #218):
> how hard it would be porting to darktable

i’m out of this game, but i suppose it’s tedious. you’d probably have to do it 2x (cpu and opencl) and judging by some other modules and their counterparts in vkdt, it’ll be something like 10x-100x slower. there’s also a thing about cropped roi/multi-pipeline processing and gtk gui that will be extra work. vkdt has a DAG, not a linear pipeline, so i can route the required lut textures easily. no idea how that’s done in dt nowadays.

---

## #220 **** (@g-man) · 2025-03-12 13:22

> **@streetfighter** (帖子 #217):
> @arctic have you considered adding the logic as a module in darktable as opposed to packaging it as a separate tool?

I think of this tool as a proof of concept and rapid development. Andrea highlights this in his original post. Once the process is nailed down, then i can see it being replicated into other software based on the current license (GPL3).

For now, we wait for this awesome work.

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

---

## #221 **Andrea** (@arctic) · 2025-03-13 00:21

> **@streetfighter** (帖子 #217):
> @arctic have you considered adding the logic as a module in darktable as opposed to packaging it as a separate tool?

I agree with the answers by [@hanatos](/u/hanatos), [@mikae1](/u/mikae1), and [@g-man](/u/g-man)!

Consider this python project a bit of a tech demo for now. The output is ok, and there is potential, but I am still exploring and refining things. Since one month ago, for example, it improved a lot, thanks to the feedback and contributions starting from this forum! I am very glad of this!

> **@sguyader** (帖子 #215):
> For video color grading, colorists often use the Kodak 2383 instead of the 2393.

I digitized the plots from the datasheet of Kodak 2383 (still haven’t committed, I wanna check a few other things).

It looks more vibrant and colorful than 2393. Overall I find the output produced by 2383 data more appealing. If we believe that what we are predicting with the simulation is close enough to real life, I see why it is preferred. Sims with 2383 data look less neutral, though.

(left) kodak vision3 50d and 2383, (right) 2393

[[![desert_kodak_vision3_50d_kodak_2383_default](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/b/5b38a2d1d348fd3485e6da1047d53a780ab64e5b_2_330x220.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/b/5b38a2d1d348fd3485e6da1047d53a780ab64e5b_2_330x220.jpeg)

desert_kodak_vision3_50d_kodak_2383_default3000×2000 742 KB](/uploads/short-url/d0YN66IcIJ5OE0TBIsoXz5E6UHx.jpeg?dl=1)

[[![desert_kodak_vision3_50d_kodak_2393_default](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/e/be76870476005bdc3546cab0c213fe55c02d1a21_2_330x220.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/e/be76870476005bdc3546cab0c213fe55c02d1a21_2_330x220.jpeg)

desert_kodak_vision3_50d_kodak_2393_default3000×2000 691 KB](/uploads/short-url/raUF7jGRp4qR0RgA7FuNwqmuEIF.jpeg?dl=1)

(left) kodak vision3 50d and 2383, (right) 2393

[[![kodak_vision3_50d_kodak_2383_default](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/4/0433e82ed8866167429a98e4820ab2c0aef8e39c_2_330x480.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/4/0433e82ed8866167429a98e4820ab2c0aef8e39c_2_330x480.jpeg)

kodak_vision3_50d_kodak_2383_default1998×3000 615 KB](/uploads/short-url/Bb7rr8f2YnJww5SidyzTT9Nq7q.jpeg?dl=1)

[[![kodak_vision3_50d_kodak_2393_default](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/f/1ffe53156a2149fa2ca6a9ca904ecd9abddb0a44_2_330x480.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/f/1ffe53156a2149fa2ca6a9ca904ecd9abddb0a44_2_330x480.jpeg)

kodak_vision3_50d_kodak_2393_default1998×3000 589 KB](/uploads/short-url/4z1GK5D5tAjGRUbPW23govHsW1K.jpeg?dl=1)

(left) kodak vision3 50d and 2383, (right) 2393

[[![sunset_crop_girl_kodak_vision3_50d_kodak_2383_default](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/5/154d0eea2030c2ede6d25c418af429db780f79aa_2_330x480.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/5/154d0eea2030c2ede6d25c418af429db780f79aa_2_330x480.jpeg)

sunset_crop_girl_kodak_vision3_50d_kodak_2383_default2000×3000 534 KB](/uploads/short-url/32r7Evd431YuTv8eW3JQ6Sm9gn0.jpeg?dl=1)

[[![sunset_crop_girl_kodak_vision3_50d_kodak_2393_default](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/c/5ca19c8e4051920046f2f699dab98d83e6ca7202_2_330x480.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/c/5ca19c8e4051920046f2f699dab98d83e6ca7202_2_330x480.jpeg)

sunset_crop_girl_kodak_vision3_50d_kodak_2393_default2000×3000 504 KB](/uploads/short-url/ddsb3QG70qlhih9nnD7aJVKxNSO.jpeg?dl=1)

Everything else default with the current `main` branch. Just loaded an image and computed the output.

> **@hanatos** (帖子 #219):
> i think i’m nearing feature completeness with this. here is the module documentation draft, including some explanations from @arctic’s OP.

That’s a nice condensed summary from the original post. Well done!

I was wondering about these parameters:

- `filter m` when exposing the print paper, dial in this share of magenta filter
- `filter y` when exposing the print paper, dial in this share of yellow filter
- `tune m` fine tune the magenta filter. think of this as a red/green tint
- `tune y` fine tune the yellow filter. think of this as a warm/cold white balance temperature

Are `filter m` and `filter y` the neutral fitted filter values?

---

## #222 **Cameron Rad** (@cameronrad) · 2025-03-13 03:20

Here some images with a 2383 and 2393 3D LUT applied. This is a LUT from Koji.

2383 Left / 2393 Right

<div class="lightbox-wrapper">[[![2383](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/f/ff930131b5b0726ddd6590368b8bbb12fe0678ac_2_690x524.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/f/ff930131b5b0726ddd6590368b8bbb12fe0678ac_2_690x524.jpeg)

23834096×3112 12.1 MB](/uploads/short-url/AsUI56GrsksQRDjMAsqWRmUkw7q.jpeg?dl=1)

[[![2393](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/f/9fa8ae7d15d1c409722e4ee9d76ff60f2e12eba9_2_690x524.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/f/9fa8ae7d15d1c409722e4ee9d76ff60f2e12eba9_2_690x524.jpeg)

23934096×3112 12.2 MB](/uploads/short-url/mMpjCrWuhwtMClU5UeNLVRUEYKR.jpeg?dl=1)

</div>

<div class="lightbox-wrapper">[[![5219_2383](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/8/5856ccfa467972c52222cb6bb4dc245b019b76de_2_690x525.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/8/5856ccfa467972c52222cb6bb4dc245b019b76de_2_690x525.jpeg)

5219_23834152×3164 19.2 MB](/uploads/short-url/cBtZc8wUeioLQGRuQlkG5NN3dLM.jpeg?dl=1)

[[![5219_2393](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/9/89468ceed346ee8ac2347db6988098241e1e2765_2_690x525.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/9/89468ceed346ee8ac2347db6988098241e1e2765_2_690x525.jpeg)

5219_23934152×3164 19.8 MB](/uploads/short-url/jAozatAQ5gyo6H1asOUvDnGWeZT.jpeg?dl=1)

</div>

Adobe also has a couple built in simulations/LUTs. Here’s their versions.

2383 left / 2393 right.

<div class="lightbox-wrapper">[[![2383 Adobe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/e/5ecfc9f557a27824e573a44e9b9a7de9c52733ea_2_690x524.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/e/5ecfc9f557a27824e573a44e9b9a7de9c52733ea_2_690x524.jpeg)

2383 Adobe4096×3112 9.51 MB](/uploads/short-url/dwK4cXnsk6z3skKqWEWlfOz3d2y.jpeg?dl=1)

[[![2393 Adobe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/8/680ae00961a68b2ca3ff731fee51d9a347e5f746_2_690x524.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/8/680ae00961a68b2ca3ff731fee51d9a347e5f746_2_690x524.jpeg)

2393 Adobe4096×3112 9.62 MB](/uploads/short-url/eQoXjZqTNC8j8XUibHaV8vaPVEa.jpeg?dl=1)

</div>

Here’s also three different 2383 LUTs applied to the same test image. Left is Koji 2383, Middle is Resolve 2383 (D60), Right is another 2383 LUT that normally has a whitepoint around D55 but I adapted it for this example.

<div class="lightbox-wrapper">[[![2383-1](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/f/ff930131b5b0726ddd6590368b8bbb12fe0678ac_2_690x524.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/f/ff930131b5b0726ddd6590368b8bbb12fe0678ac_2_690x524.jpeg)

2383-14096×3112 12.1 MB](/uploads/short-url/AsUI56GrsksQRDjMAsqWRmUkw7q.jpeg?dl=1)

[[![2383-2](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/b/bbcabb71692b64cc8cf72c30547744f7102896fd_2_690x524.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/b/bbcabb71692b64cc8cf72c30547744f7102896fd_2_690x524.jpeg)

2383-24096×3112 12.1 MB](/uploads/short-url/qNhDBbVjZa11BxrvWwpHU9yRM9T.jpeg?dl=1)

[[![2383-3](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/2/82f2c0a40310a11a371fdbca2905c8c3a7c4650b_2_690x524.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/2/82f2c0a40310a11a371fdbca2905c8c3a7c4650b_2_690x524.jpeg)

2383-34096×3112 12.3 MB](/uploads/short-url/iGqai5DuOScvZf3s7TBICJmilVV.jpeg?dl=1)

</div>

Here are the Resolve 2383 LUTs at different whitepoints. D55, D60, D65.

<div class="lightbox-wrapper">[[![2383-d55](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/e/be6e1460fd9b0a528f26c864a8871e9f166f8f03_2_690x524.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/e/be6e1460fd9b0a528f26c864a8871e9f166f8f03_2_690x524.jpeg)

2383-d554096×3112 12 MB](/uploads/short-url/raCyXrxquUtacZBBwW90A60M2lB.jpeg?dl=1)

[[![2383-d60](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/b/bbcabb71692b64cc8cf72c30547744f7102896fd_2_690x524.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/b/bbcabb71692b64cc8cf72c30547744f7102896fd_2_690x524.jpeg)

2383-d604096×3112 12.1 MB](/uploads/short-url/qNhDBbVjZa11BxrvWwpHU9yRM9T.jpeg?dl=1)

[[![2383-d65](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/c/ac4360eb1483159ab3c09f9948168be3a1ce9851_2_690x524.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/c/ac4360eb1483159ab3c09f9948168be3a1ce9851_2_690x524.jpeg)

2383-d654096×3112 12.2 MB](/uploads/short-url/ozUtWarlajQSK96mGXKJ6xYJHXz.jpeg?dl=1)

</div>

---

## #223 **jo** (@hanatos) · 2025-03-13 07:09

> **@arctic** (帖子 #221):
> Are filter m and filter y the neutral fitted filter values?

right, these come straight out of the neutral fitter. i was hoping to hide them from the ui/show only in some advanced setting and only display the `tune` counterparts. the final filter weight is then just `filter m + tune m * 0.1` and clamped to <span class="math">[0,1]</span>.

---

## #224 **Sébastien Guyader** (@sguyader) · 2025-03-13 12:20

> **@arctic** (帖子 #221):
> If we believe that what we are predicting with the simulation is close enough to real life, I see why it is preferred. Sims with 2383 data look less neutral, though.

The 2383 definitely has a look, which is why it is quite widely appreciated and used by film makers and colorists. I like the results you got with it!

---

## #225 **Andrea** (@arctic) · 2025-03-14 12:27

Thanks [@cameronrad](/u/cameronrad), that’s a nice comparison.

There is already variability among those three sources.

I wonder how are this LUTs made? Do you have any insight about that?

Since the look of print paper (or print film) is really achieved only after projecting a negative, I wonder how they can isolate the LUT for only the final printing medium. I guess severe assumptions on the input need to be made. Or maybe “Vision3 input” is somehow assumed.

2383 looks somewhat warmer and more stylized also in your comparisons, from Koji and Adobe. That is a good sign, and it aligns with the results we get from `agx-emulsion` and the data from the technical documents.

When you say that the LUT is optimized for a white point, do you mean that neutral gray input is giving a different tint at the output according to the white point?

---

## #226 **jo** (@hanatos) · 2025-03-14 17:54

now that most of the agx-emulsion pipeline is implemented in vkdt, i’m going over it once more in more detail to find differences and find out which of these are problems or just different…

i’m still unsure whether my noise model is comparable to yours, doing some more tests on a synthetic ramp (worth pointing out that this runs through a virtual ND filter that is not a linear transmittance ramp, only for the left half or so it’s close).

i use a procedural noise pattern to compute the variation of grain numbers in each pixel. this is kinda the poisson part. then i use a binomial to sample whether or not these grains turn. the binomial distribution has some built-in variance reduction at the rims, for p=0 and p=1. not sure why i can’t see this in your plots, i believe because the poission part dominates so much? or maybe because i’m using the large-N gaussian approximation for the binomial.

anyways, here are some results: the waveform histogram shows straight value, not standard deviation as your grain plots above, but you can also see how the variance compresses towards the extremes (white/black). increasing exposure of the ramp:

[[![2025-03-14-152757_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/6/96396c90b536c5cd6751a6479da72f9f473670b4_2_690x457.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/6/96396c90b536c5cd6751a6479da72f9f473670b4_2_690x457.png)

2025-03-14-152757_hyprshot1384×918 235 KB](/uploads/short-url/lqWEmORBpgoVD5ubm5RAUDyjBPu.png?dl=1)

[[![2025-03-14-152811_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/1/91b84a73de673e1f1ac7ade4aba3b53c2895bb75_2_690x457.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/1/91b84a73de673e1f1ac7ade4aba3b53c2895bb75_2_690x457.png)

2025-03-14-152811_hyprshot1384×918 223 KB](/uploads/short-url/kN64Cn4Y6RpHglVKmHLHBaAKPul.png?dl=1)

[[![2025-03-14-152822_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/6/06bb59b4de666fe9ec47e11a6a770796f306abef_2_690x457.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/6/06bb59b4de666fe9ec47e11a6a770796f306abef_2_690x457.png)

2025-03-14-152822_hyprshot1384×918 191 KB](/uploads/short-url/XygccjCgLQ8IML0IVjZPcT4Mph.png?dl=1)

this is with lower `uniform` parameter, which means variation of the number of grains in each pixel, giving an overall more granular look. this adds another source of variance, hence the point cloud in the waveform explodes. the size of the grains makes no difference, since it’s integrated away over the height of the test strip.

[[![2025-03-14-152844_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/2/0220f3058bc38c31377a91ed7083eceef1c9aa59_2_690x457.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/2/0220f3058bc38c31377a91ed7083eceef1c9aa59_2_690x457.png)

2025-03-14-152844_hyprshot1384×918 348 KB](/uploads/short-url/iPy0qnQxWkd7Zcq19bom7j0z8d.png?dl=1)

this is the negative, very under exposed (-5ev) to stretch the range, shows some quantisation artifacts in the deep to-be-blacks on the right end of the test strip:

[[![2025-03-14-154551_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/3/43936912cb924c7be06cc360580641266a62d1d7_2_690x457.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/3/43936912cb924c7be06cc360580641266a62d1d7_2_690x457.png)

2025-03-14-154551_hyprshot1384×918 208 KB](/uploads/short-url/9DNOAsO5VOiYN2L0xTGjtpzkwSj.png?dl=1)

this one is with `uniform=1` but setting it to zero just increases variance overall, except for in the blacks where it stays the same as in the above image.

for completeness here’s the processing graph `.cfg` file:

[test.cfg](/uploads/short-url/u3byV9CwQnxDETiJ91It1gKNkn1.cfg) (1.6 KB)

i have to stare at these strips for a bit more, but i think the noise model might fall into the category “different but i’m happy with it”. i probably want to change the parameters around, maybe a combo box with a few ISO speed ratings.

---

## #227 **nosle** (@nosle) · 2025-03-14 19:25

Just a quick comment, I compiled an hour or so ago and Endura premium seems to be the only paper that looks reasonable. Now I don’t know what I’m doing with vtkd so take it with a grain of salt. The sims look kind of ok with Endura though. The other papers are very yellowish.

The grain as seen when turning on “simulate grain” looks really quite strange and nothing like the agx app. It’s very contrasty and pixly, not very analogue looking.

Also wondering if paper exposure works the same in both apps? Feels different i vktd.

---

## #228 **** (@qosch) · 2025-03-14 23:39

I played a bit with it in vkdt, and it is quite fun to work with, but even spending lots of time, I cannot get out an image that doesn’t look “over the top”.

I’m not using the grain stuff for now and am leaving the couplers at 0 for now. Tune m and tune y seem to act as something like a white balance. So after adjusting m and y to get neutral colors, there are film and paper as well as 4 sliders remaining, of which 2 of each seem to do mostly the same thing.

Concerning film and paper, I started with Porta 400 and Porta Endura.

What does your graph in the node editor look like? I’m using this for now:

[[![grafik](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/1/b16326ec826c10d6650ec3c8193da5799699c7ab_2_690x190.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/1/b16326ec826c10d6650ec3c8193da5799699c7ab_2_690x190.png)

grafik1972×544 69.4 KB](/uploads/short-url/pjeWyQudplRWzsEOat7BKePQcDV.png?dl=1)

Disabling filmsim, what should the image look like? Correctly white balanced and exposed, I suppose?

I also wouldn’t mind a cfg file to compare results just to be sure there is no AMD exclusive bug involved

[![:wink:](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)

---

## #229 **jo** (@hanatos) · 2025-03-15 17:54

next up: the weird colour cast i’ve seen since the beginnig. i printed all buffers of log spectral power and density etc and compared to the corresponding agx output. of course they kinda diverge, i.e. earlier stages are more similar. the enlarger with thungsten vs 3200K and the filter transmittances make quite a bit of a difference.

turns out the initial film exposure step was calibrated to 1ev brighter on my side as it was on agx-emulsion code.

also: if density is NaN this means infinite density, not zero

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 which was quite the change. anyways i’ll spare you with the debugging output, maybe one example, the negative of the test image:

[[![vkdt-scan-negative](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/5/5511121814504dcf08926056d74cd6749c8be0b2.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/5/5511121814504dcf08926056d74cd6749c8be0b2.jpeg)

vkdt-scan-negative512×256 14 KB](/uploads/short-url/c8x9QeRrIvw8UyU27bHjUAZ8Fiy.jpeg?dl=1)

[[![agx-scan-negative](https://d2x313g9lpht1q.cloudfront.net/original/3X/8/6/864721baf574db4cac04ceeec74bc2479abdf026.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/8/6/864721baf574db4cac04ceeec74bc2479abdf026.png)

agx-scan-negative512×256 27.5 KB](/uploads/short-url/j9SnzdRsXDOuoeknwNRRVLzU778.png?dl=1)

and a final render with default settings and everything fancy disabled in agx-emulsion and the corresponding vkdt render:

<div class="lightbox-wrapper">[[![agx-img](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/b/bb87f248ba56c8ad92c16bd8560fb8c167d692c9_2_332x500.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/b/bb87f248ba56c8ad92c16bd8560fb8c167d692c9_2_332x500.jpeg)

agx-img3733×5610 2.64 MB](/uploads/short-url/qKYy9qFKeXZiwvAsBNaUqRAjggx.jpeg?dl=1)

[[![vkdt-img](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/4/5406c7e553c1f18b0ea9f212717e7016f52f3fe2_2_332x500.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/4/5406c7e553c1f18b0ea9f212717e7016f52f3fe2_2_332x500.jpeg)

vkdt-img3735×5610 5.64 MB](/uploads/short-url/bZkDovfddp8ZHRxCIvx36mQ5glQ.jpeg?dl=1)

</div>

both use like -0.5 ev print exposure, no auto exposure. i had to tune the m and y filters in vkdt a bit, but not all that much (not aiming for best match here, just eyeballed from far away for a few seconds, you can tell by the background). now re-fitting all the neutral values, i think i can finally leave `filter c` at a constant and get valid values for the two others. big step towards equivalent output i think. science is only magic if it’s really completely correct…

---

## #230 **Andrea** (@arctic) · 2025-03-17 16:03

Just judging by the waveforms the grain does seams to behave quite well, and it responds to uniformity as I would expect.

> **@hanatos** (帖子 #226):
> i use a procedural noise pattern to compute the variation of grain numbers in each pixel. this is kinda the poisson part. then i use a binomial to sample whether or not these grains turn. the binomial distribution has some built-in variance reduction at the rims, for p=0 and p=1. not sure why i can’t see this in your plots, i believe because the poission part dominates so much? or maybe because i’m using the large-N gaussian approximation for the binomial.

At the extremes of the density values I use `density_min` (i.e. the fog) to lift the variance when density (over base + fog) is close to zero, and as you mention I reduce `uniformity` to increase the variance close to density max. I am recalling the next plot for reference. In that simplified script I omitted `density_min`, but it would lift the left part of the graph.

Is this you were referring to?

> **@arctic** (帖子 #130):
> image584×432 50.3 KB
image584×432 50.3 KB

As a comment, when printing on paper the effect of fog or uniformity might not be very visible. Most of the time we are printing only the “linear part” of the negative. So the behavior for p=0 or p=1, is mostly relevant for simulating underexposure or overexposure.

> **@hanatos** (帖子 #226):
> i have to stare at these strips for a bit more, but i think the noise model might fall into the category “different but i’m happy with it”. i probably want to change the parameters around, maybe a combo box with a few ISO speed ratings.

When comparing with real ISO speed ratings and RMS granularity I usually compute a test image with a ramp (as yours), and a pixel size equal to the area of the aperture of the densitometer used in the measurements (circular with a diameter of 48um). Standard deviation times 1000 should be tune to be close to the measured values, and for different pixel sizes we trust the particle model to scale well. The usual range of RMS granularity for color film is 5-30, depending on ISO.

---

## #231 **Andrea** (@arctic) · 2025-03-17 16:19

> **@hanatos** (帖子 #229):
> turns out the initial film exposure step was calibrated to 1ev brighter on my side as it was on agx-emulsion code.

This indeed can add some casts that happens with over-exposures, more strong in consumer films. Portra 400 instead is more invariant.

> **@hanatos** (帖子 #229):
> now re-fitting all the neutral values, i think i can finally leave filter c at a constant and get valid values for the two others. big step towards equivalent output i think. science is only magic if it’s really completely correct…

That is also a very good sing! According to real life, the cyan filter should also be set to zero, but I cannot really make them work in that way because I would need negative values for magenta filters.

The comparison in the portrait is also getting closer, In the example still some residual magenta tint that could be adjusted with the m-filter most likely.

I am experimenting a bit with the profile making scripts. There are a few parts that I am rethinking about the sensitivity unmixing. Especially because I want to experiment with tungsten balanced film, that I believe would not work well right now.

In the weekend I added some more film data:

- Ektar 100
- the missing ones from the Portra family: 160, 800, 800 (push 1 stop), 800 (push 2 stops)

I quite like the profile of Ektar 100

[![:star_struck:](https://discuss.pixls.us/images/emoji/apple/star_struck.png?v=12)](https://discuss.pixls.us/images/emoji/apple/star_struck.png?v=12)

---

## #232 **jo** (@hanatos) · 2025-03-17 17:42

> **@arctic** (帖子 #231):
> In the weekend I added some more film data:

saw that! struggling with the white balance as we speak. did you use the LED lights for 2383 and 2392 now? and how do you fit? what works best for me currently is some completely idiotic random search of the whole domain, followed by refinement with nelder mead.

---

## #233 **** (@mikae1) · 2025-03-17 20:19

> **@arctic** (帖子 #231):
> In the weekend I added some more film data:

Ektar 100
the missing ones from the Portra family: 160, 800, 800 (push 1 stop), 800 (push 2 stops)

I quite like the profile of Ektar 100

Cool! I just downloaded [https://github.com/andreavolpato/agx-emulsion/archive/refs/heads/main.zip](https://github.com/andreavolpato/agx-emulsion/archive/refs/heads/main.zip) but the only new film I see is kodak_vision3_50d. kodak_ektar_100 is not there as an example.

Seems it should be there according to [https://github.com/andreavolpato/agx-emulsion/commit/fa5956c9aae8821a23602851452d652b7e32f0e6](https://github.com/andreavolpato/agx-emulsion/commit/fa5956c9aae8821a23602851452d652b7e32f0e6). Strange?

---

## #234 **Andrea** (@arctic) · 2025-03-17 22:50

For the cine color print film I used the same 3200K (tungsten-halogen). The data looks a bit strange especially for 2393, there is some thinking to be done. It is not clear what are the experimental conditions when measuring density curves and sensitivities, and how I should take this into account to better balance the profiles and make them more compatible to the virtual enlarger.

For all the film stock I added in the enlarger a heat filter (Schott KG3), plus the transmission of a real lens, to imitate the enlarger lens. Apparently lenses with normal glass cut the UV from around 400-380 nm.

In the end the total filter looks very similar to what used in the virtual camera. So probably I will substitute it with a generic filter without relying on the actual experimental data.

[[![heat_filter_lens_transmittance](https://d2x313g9lpht1q.cloudfront.net/original/3X/1/5/15c292eab55e44bcd866bdc1d6cf6dd26c061d4c.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/1/5/15c292eab55e44bcd866bdc1d6cf6dd26c061d4c.png)

heat_filter_lens_transmittance640×480 29.2 KB](/uploads/short-url/36uTLLRqx1hO3K77IDxMpS7VrMo.png?dl=1)

I did change also the dichroic filters of the enlarger, I found a remote PDF with measurments of the real dichroics of a Durst enlarger ([http://www.jollinger.com/photo/cam-coll/manuals/enlargers/durst/Durst_Enlarger_Guide.pdf](http://www.jollinger.com/photo/cam-coll/manuals/enlargers/durst/Durst_Enlarger_Guide.pdf)). In my opinion they are better optimized for the transitions of the dyes and absorptions of the paper. Thorlabs and Edmund Optics ones are generic for a wide range of applications, and they are more “leaky”.

[[![thorlabs](https://d2x313g9lpht1q.cloudfront.net/original/3X/8/e/8e366dcbabb574b590695436e141b64c7f96ce22.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/8/e/8e366dcbabb574b590695436e141b64c7f96ce22.png)

thorlabs640×219 21.7 KB](/uploads/short-url/ki4pG25gxegqci4DMrNY7HEBQeS.png?dl=1)

[[![edmund_optics](https://d2x313g9lpht1q.cloudfront.net/original/3X/e/4/e4443572e2b326320234e32b88aa5175968f7086.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/e/4/e4443572e2b326320234e32b88aa5175968f7086.png)

edmund_optics640×219 21.7 KB](/uploads/short-url/wzkZZEeQPfNhU3flxoQkFmxlw8K.png?dl=1)

[[![durst_digital_light](https://d2x313g9lpht1q.cloudfront.net/original/3X/e/4/e4e7a44c814b779ef150e483089c3ad724e09112.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/e/4/e4e7a44c814b779ef150e483089c3ad724e09112.png)

durst_digital_light640×219 21.9 KB](/uploads/short-url/wEZ9w6BINAVceajkCn95d6EXhlg.png?dl=1)

---

## #235 **Andrea** (@arctic) · 2025-03-17 23:02

> **@mikae1** (帖子 #233):
> Strange?

That is strange indeed. I see the data when downloading in the `main.zip` file.

I did another small commit, maybe you can try again.

I also saw [@Y69](/u/y69) doing a very nice play raw with Ektar 100.

---

## #236 **jo** (@hanatos) · 2025-03-18 07:40

> **@nosle** (帖子 #227):
> Just a quick comment, I compiled an hour or so ago and Endura premium seems to be the only paper that looks reasonable. Now I don’t know what I’m doing with vtkd

> **@qosch** (帖子 #228):
> I played a bit with it in vkdt, and it is quite fun to work with, but even spending lots of time, I cannot get out an image that doesn’t look “over the top”.

i don’t want to hijack arctic’s thread here, where the discussion about new film stocks and the spectral model takes place… maybe start a new thread specifically about mondane vkdt bugs? i pushed some fixes and the new films (portra family + ektar), breaking old cfg files in the process, so maybe some things are already fixed. to make the grain look really very good i think i want to look at some properties here in more detail.

> **@arctic** (帖子 #234):
> For all the film stock I added in the enlarger a heat filter (Schott KG3), plus the transmission of a real lens, to imitate the enlarger lens. Apparently lenses with normal glass cut the UV from around 400-380 nm.

hah, really nice. i think the shape of this “envelope” function looks pretty much like what i had dialed in by hand: quick slope from 380 to 400 and slower decay towards 800nm. it’s probably a difference though where the filter is applied. i have it at the very beginning of the pipeline, assuming that the wavelengths don’t exchange energy until the very end (see my comment about fluorescence), but this is incorrect. the way the density is formed totally allows for some cross talk between wavelengths, so it’s probably important to apply the filter in the print exposure stage.

> **@arctic** (帖子 #234):
> I did change also the dichroic filters of the enlarger, I found a remote PDF with measurments of the real dichroics of a Durst enlarger

…and this one is more like my smooth approximation that sums the filters to one when they transition! this way easier/more robust to fit, and i was kinda proud i could converge the thorlabs-like filters for all film/paper combinations now. i shall try the durst-like filters too.

---

## #237 **** (@mikae1) · 2025-03-18 10:01

> **@arctic** (帖子 #235):
> That is strange indeed. I see the data when downloading in the main.zip file.
I did another small commit, maybe you can try again.
I also saw @Y69 doing a very nice play raw with Ektar 100.

Deleted the old agx-emulsion directory and downloaded master again. After that I ran:

```
uv run --python 3.11 --with-requirements requirements.txt --no-project --with-editable .
uv run --python 3.11 --with-requirements requirements.txt --no-project --with-editable . agx_emulsion/gui/main.py

```

Still no go. I have:

- kodak_portra_400
- kodak_ultramax_400
- kodak_gold_200
- kodak_vision3_50d
- fujifilm_pro_400h
- fujifilm_xtra_400
- fujifilm_c200

[![:woozy_face:](https://discuss.pixls.us/images/emoji/apple/woozy_face.png?v=12)](https://discuss.pixls.us/images/emoji/apple/woozy_face.png?v=12)

 I’ll wait and see if it gets solved with a later code update.

---

## #238 **Benjamin** (@piratenpanda) · 2025-03-18 10:14

Is anyone running this on mesa 25 and amd hardware? I use arch and I can’t get napari showing up properly. All other stuff like glxgears etc work just fine so I am really lost what I could be missing. The error is

<pre data-code-wrap="python"><code class="lang-python">WARNING: qglx_findConfig: Failed to finding matching FBConfig for QSurfaceFormat(version 2.0, options QFlags<QSurfaceFormat::FormatOption>(), depthBufferSize 0, redBufferSize 1, greenBufferSize 1, blueBufferSize 1, alphaBufferSize 0, stencilBufferSize 0, samples 0, swapBehavior QSurfaceFormat::SingleBuffer, swapInterval 1, colorSpace QSurfaceFormat::DefaultColorSpace, profile QSurfaceFormat::NoProfile)
WARNING: qglx_findConfig: Failed to finding matching FBConfig for QSurfaceFormat(version 2.0, options QFlags<QSurfaceFormat::FormatOption>(), depthBufferSize 0, redBufferSize 1, greenBufferSize 1, blueBufferSize 1, alphaBufferSize 0, stencilBufferSize 0, samples 0, swapBehavior QSurfaceFormat::SingleBuffer, swapInterval 1, colorSpace QSurfaceFormat::DefaultColorSpace, profile QSurfaceFormat::NoProfile)
WARNING: Could not initialize GLX
</code></pre>

when using “export QT_XCB_GL_INTEGRATION=none” I get a black window which has clickable menus and stuff but I can’t see anything.

Any pointers would be highly appreciated.

Edit: Found the solution here:

[https://www.reddit.com/r/NobaraProject/comments/1fb2o4v/after_updating_to_nobara40_anaconda_navigator_not/](https://www.reddit.com/r/NobaraProject/comments/1fb2o4v/after_updating_to_nobara40_anaconda_navigator_not/)

`conda install -c conda-forge libstdcxx-ng` does the trick. Now on to playing

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

---

## #239 **** (@mikae1) · 2025-03-18 10:53

> **@hanatos** (帖子 #236):
> i don’t want to hijack arctic’s thread here, where the discussion about new film stocks and the spectral model takes place… maybe start a new thread specifically about mondane vkdt bugs?

Can only speak for myself, but it doesn’t bother me that both types of conversation takes place in this thread.

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

I like following the development even if I only understand a tiny fraction of what you’re talking about.

[![:smiley:](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)

---

## #240 **Sébastien Guyader** (@sguyader) · 2025-03-18 11:29

> **@mikae1** (帖子 #237):
> Still no go. I have:

kodak_portra_400
kodak_ultramax_400
kodak_gold_200
kodak_vision3_50d
fujifilm_pro_400h
fujifilm_xtra_400
fujifilm_c200

 I’ll wait and see if it gets solved with a later code update.

I cloned the repository using `git`, and all the latest additions are here.

---

## #241 **Y** (@Y69) · 2025-03-18 13:43

In my case, I had simply pulled (`git pull origin main`) the changes.

When I use your link and download the main branch snapshot as ZIP file it contains the new simulation data. Verify the following path exists: `agx-emulsion-main/agx_emulsion/data/film/negative/kodak_ektar_100/`.

---

## #242 **** (@mikae1) · 2025-03-18 13:52

> **@Y69** (帖子 #241):
> Verify the following path exists: agx-emulsion-main/agx_emulsion/data/film/negative/kodak_ektar_100/.

kodak_ektar_100 showed up in napari as I earlier wrote. Not the other ones (like kodak_portra_800_push2) though. Seems they’re all there but they don’t show up in napari.

```
agx-emulsion/agx_emulsion/data/film/
├── negative
│ ├── fujifilm_c200
│ │ ├── density_curve_b.csv
│ │ ├── density_curve_g.csv
│ │ ├── density_curve_r.csv
│ │ ├── dye_density_mid.csv
│ │ ├── dye_density_min.csv
│ │ ├── info.txt
│ │ ├── log_sensitivity_b.csv
│ │ ├── log_sensitivity_g.csv
│ │ └── log_sensitivity_r.csv
│ ├── fujifilm_pro_400h
│ │ ├── density_curve_b.csv
│ │ ├── density_curve_g.csv
│ │ ├── density_curve_r.csv
│ │ ├── dye_density_mid.csv
│ │ ├── dye_density_min.csv
│ │ ├── info.txt
│ │ ├── log_sensitivity_b.csv
│ │ ├── log_sensitivity_g.csv
│ │ └── log_sensitivity_r.csv
│ ├── fujifilm_xtra_400
│ │ ├── density_curve_b.csv
│ │ ├── density_curve_g.csv
│ │ ├── density_curve_r.csv
│ │ ├── dye_density_mid.csv
│ │ ├── dye_density_min.csv
│ │ ├── info.txt
│ │ ├── log_sensitivity_b.csv
│ │ ├── log_sensitivity_g.csv
│ │ └── log_sensitivity_r.csv
│ ├── generic_a
│ │ ├── dye_density_c.csv
│ │ ├── dye_density_m.csv
│ │ ├── dye_density_y.csv
│ │ └── info.txt
│ ├── kodak_ektar_100
│ │ ├── density_curve_b.csv
│ │ ├── density_curve_g.csv
│ │ ├── density_curve_r.csv
│ │ ├── dye_density_mid.csv
│ │ ├── dye_density_min.csv
│ │ ├── info.txt
│ │ ├── log_sensitivity_b.csv
│ │ ├── log_sensitivity_g.csv
│ │ └── log_sensitivity_r.csv
│ ├── kodak_gold_200
│ │ ├── density_curve_b_corrected.csv
│ │ ├── density_curve_b.csv
│ │ ├── density_curve_g.csv
│ │ ├── density_curve_r.csv
│ │ ├── dye_density_mid.csv
│ │ ├── dye_density_min.csv
│ │ ├── info.txt
│ │ ├── log_sensitivity_b.csv
│ │ ├── log_sensitivity_g.csv
│ │ └── log_sensitivity_r.csv
│ ├── kodak_portra_160
│ │ ├── density_curve_b.csv
│ │ ├── density_curve_g.csv
│ │ ├── density_curve_r.csv
│ │ ├── dye_density_mid.csv
│ │ ├── dye_density_min.csv
│ │ ├── info.txt
│ │ ├── log_sensitivity_b.csv
│ │ ├── log_sensitivity_g.csv
│ │ └── log_sensitivity_r.csv
│ ├── kodak_portra_400
│ │ ├── density_curve_b.csv
│ │ ├── density_curve_g.csv
│ │ ├── density_curve_r.csv
│ │ ├── dye_density_mid.csv
│ │ ├── dye_density_min.csv
│ │ ├── info.txt
│ │ ├── log_sensitivity_b.csv
│ │ ├── log_sensitivity_g.csv
│ │ └── log_sensitivity_r.csv
│ ├── kodak_portra_800
│ │ ├── density_curve_b.csv
│ │ ├── density_curve_g.csv
│ │ ├── density_curve_r.csv
│ │ ├── dye_density_mid.csv
│ │ ├── dye_density_min.csv
│ │ ├── info.txt
│ │ ├── log_sensitivity_b.csv
│ │ ├── log_sensitivity_g.csv
│ │ └── log_sensitivity_r.csv
│ ├── kodak_portra_800_push1
│ │ ├── density_curve_b.csv
│ │ ├── density_curve_g.csv
│ │ ├── density_curve_r.csv
│ │ └── info.txt
│ ├── kodak_portra_800_push2
│ │ ├── density_curve_b.csv
│ │ ├── density_curve_g.csv
│ │ ├── density_curve_r.csv
│ │ └── info.txt
│ ├── kodak_ultramax_400
│ │ ├── density_curve_b.csv
│ │ ├── density_curve_g.csv
│ │ ├── density_curve_r.csv
│ │ ├── dye_density_mid.csv
│ │ ├── dye_density_min.csv
│ │ ├── info.txt
│ │ ├── log_sensitivity_b.csv
│ │ ├── log_sensitivity_g.csv
│ │ └── log_sensitivity_r.csv
│ └── kodak_vision3_50d
│ ├── density_curve_b.csv
│ ├── density_curve_g.csv
│ ├── density_curve_r.csv
│ ├── dye_density_c.csv
│ ├── dye_density_m.csv
│ ├── dye_density_mid.csv
│ ├── dye_density_min.csv
│ ├── dye_density_y.csv
│ ├── log_sensitivity_b.csv
│ ├── log_sensitivity_g.csv
│ └── log_sensitivity_r.csv
└── positive
 └── fujifilm_provia_100f
 ├── density_curve_b.csv
 ├── density_curve_g.csv
 ├── density_curve_r.csv
 ├── dye_density_c.csv
 ├── dye_density_m.csv
 ├── dye_density_y.csv
 ├── log_sensitivity_b.csv
 ├── log_sensitivity_g.csv
 └── log_sensitivity_r.csv

17 directories, 114 files

```

---

## #243 **jo** (@hanatos) · 2025-03-18 15:22

the new data works for me. interesting to see the subtly different looks with fitted white balance/filter weights: [https://jo.dreggn.org/filmtab/table.html](https://jo.dreggn.org/filmtab/table.html) . the portra/portra combination is certainly outstanding. i used some auto exposure, so the push variants of portra 800 look similar in overall brightness. of course needs some manual fine tuning (both exposures) to actually look great.

<details>
<summary>
script to generate the table</summary>

<pre data-code-wrap="bash"><code class="lang-bash">#!/bin/bash

films=(
kodak_ektar_100
kodak_portra_160
kodak_portra_400
kodak_portra_800
kodak_portra_800_push1
kodak_portra_800_push2
kodak_gold_200
kodak_ultramax_400
kodak_vision3_50d
fujifilm_pro_400h
fujifilm_xtra_400
fujifilm_c200
)

papers=(
kodak_endura_premier
kodak_ektacolor_edge
kodak_supra_endura
kodak_portra_endura
fujifilm_crystal_archive_typeii
kodak_2383
kodak_2393
)

n_films=${#films[@]}
n_papers=${#papers[@]}
# ${films[0]}

cat << EOF > table.html
<html>
<body>
<table style="width:100%">
EOF

echo '<tr><th>film/paper</th>' >> table.html
for paper in "${papers[@]}"
do
 echo "<th>$(echo $paper | sed -e 's/_/ /g')</th>" >> table.html
done
echo '</tr>' >> table.html

f=0
for film in "${films[@]}"
do
 p=0
 echo "<tr><td>$(echo $film | sed -e 's/_/ /g')</td>" >> table.html
 for paper in "${papers[@]}"
 do
 echo "<td><img style=\"width:12vw\" src=\"img_${film}_${paper}.jpg\"/></td>" >> table.html
 vkdt cli -d none -g img_0000.exr.cfg \
 --width 256 --height 256 \
 --quality 92 \
 --filename img_${film}_${paper} \
 --output main \
 --config "param:filmsim:01:ev film:1.0" \
 "param:filmsim:01:film:$f" \
 "param:filmsim:01:paper:$p" \
 "param:filmsim:01:filter c:-1.0"
 p=$((p+1))
 done
 echo '</tr>' >> table.html
 f=$((f+1))
done

cat << EOF >> table.html
</table>
</body>
</html>
EOF
</code></pre>

</details>

---

## #244 **Y** (@Y69) · 2025-03-18 15:40

That’s weird. I can see the others in the napari GUI:

[![20250318-163623_snap](https://d2x313g9lpht1q.cloudfront.net/original/3X/3/6/36ad5f02660d7e176a5e90d2d9bc6b6a34a5d31b.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/3/6/36ad5f02660d7e176a5e90d2d9bc6b6a34a5d31b.png)

---

## #245 **Andrea** (@arctic) · 2025-03-18 17:25

I think it is something related to the python package installation.

If you used pip with `pip install -e .`, the “-e” is necessary to create a symlink, so every change done to the package folder will be available in the installed package. You can try to uninstall and reinstall the python package.

---

## #246 **Andrea** (@arctic) · 2025-03-18 17:32

I love this comparison table!!!

[![:star_struck:](https://discuss.pixls.us/images/emoji/apple/star_struck.png?v=12)](https://discuss.pixls.us/images/emoji/apple/star_struck.png?v=12)

 I will try to make something similar with agx-emulsion so it will be easier to check the differences, especially in the more edgy combinations. The “cine print film - photographic negative” combinations are experimental and I assume never meant to be used in real life.

---

## #247 **Andrea** (@arctic) · 2025-03-18 22:12

Following your idea [@hanatos](/u/hanatos), I made a comparison table of the current default output of `agx-emulsion`.

Ektacolor Edge paper is an outlier and possibly problematic, showing a green color cast. Changing the filters I can still get good looking images from it, but in that case neutral input colors will not be neutral in the print, but with a slight magenta cast.

Overall I think that the fitted neutral filters in `agx-emulsion` do not give an always consistent output, and manual tuning is necessary to mediate slight casts and to find a compromised balance. They are nonetheless a reasonable starting point.

[[![collage](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/7/77fe35a0519f090a8bf58e5ac3846d58c9198570_2_455x1000.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/7/77fe35a0519f090a8bf58e5ac3846d58c9198570_2_455x1000.jpeg)

collage2221×4860 746 KB](/uploads/short-url/h7vsxiW5jZ3KaL4kcsTxGZhAfIY.jpeg?dl=1)

<details>
<summary>
Python script</summary>

<pre data-code-wrap="python"><code class="lang-python">from agx_emulsion.model.process import photo_params, photo_process
from agx_emulsion.model.stocks import FilmStocks, PrintPapers
from agx_emulsion.utils.io import load_image_oiio
import numpy as np
import matplotlib.pyplot as plt

image = load_image_oiio('portrait_256.tif')

N = np.size(FilmStocks)
M = np.size(PrintPapers)

photos = np.zeros((N, M, image.shape[0], image.shape[1], 3))
for i, film in enumerate(FilmStocks):
 print(i)
 for j, paper in enumerate(PrintPapers):
 params = photo_params(film.value, paper.value)
 params.negative.grain.active = False
 params.negative.halation.active = False
 params.print_paper.glare.active = False
 params.io.full_image = True
 params.scanner.unsharp_mask = (0,0)
 photos[i,j] = photo_process(image, params)

collage = np.vstack([np.hstack([photos[i,j] for j in range(M)]) for i in range(N)])
fig, ax = plt.subplots(figsize=(10,18))
ax.imshow(collage)
ax.set_yticks(image.shape[0] * np.arange(N) + image.shape[0]//2)
ax.set_yticklabels(film.name for film in FilmStocks)
ax.set_xticks(image.shape[1] * np.arange(M) + image.shape[1]//2)
ax.set_xticklabels([paper.name for paper in PrintPapers], rotation=90)
ax.xaxis.tick_top()

plt.savefig('collage.jpg', bbox_inches='tight', dpi=300)
</code></pre>

</details>

---

## #248 **Cameron Rad** (@cameronrad) · 2025-03-19 04:58

> **@arctic** (帖子 #225):
> I wonder how are this LUTs made? Do you have any insight about that?
Since the look of print paper (or print film) is really achieved only after projecting a negative, I wonder how they can isolate the LUT for only the final printing medium. I guess severe assumptions on the input need to be made. Or maybe “Vision3 input” is somehow assumed.

I’ll have to dig through my stuff to find out exactly how those LUTs were made. I know one of the 2383 LUTs is labelled as K2254-K2383. So it’s the combined effects of a intermediate film and 2383. Here’s the datasheet for 2254. [Color Digital Intermediate Film 2254](https://kodakcraftprodcontent.z13.web.core.windows.net/content/products-brochures/motion-picture/KODAK-VISION3-2254-technical-information.pdf)

---

## #249 **** (@mikae1) · 2025-03-19 07:42

> **@mikae1** (帖子 #242):
> Seems they’re all there but they don’t show up in napari.

git cloning instead of downloading the zip worked.

---

## #250 **Sakari** (@flannelhead) · 2025-03-19 22:01

Hey there [@arctic](/u/arctic) and others,

I have been enjoying this thread *a lot* - really appreciate the efforts made here.

This body of work inspired me to also start experimenting. As I’m quite familiar with the ideas behind [Blender’s picture formation](https://blenderartists.org/t/feedback-development-filmic-baby-step-to-a-v2/1361663), also called AgX coincidentally, I wanted to see how those ideas would fly for simulating a negative film + print process like you have done here.

Currently the experiment exists as a [CTL script](https://acescentral.com/knowledge-base-2/ctl/) for ART. Instead of spectral data, it works on tristimulus data in all stages and uses matrices to account for the spectral sensitivites and the dye characteristics. It implements the whole process which includes exposing the negative, converting density to transmittance, exposing the paper and reading out the reflectance. I’m not certainly the first one with this idea - I believe barselino at Mastodon has been doing something [fairly similar](https://mastodon.social/@barselino/110790980536800634) and I circled back into those posts after seeing your simulations.

In the negative and paper exposing stages, the same curve is used for all three tristimulus components, and the curves have not been matched to any particular dataset. This probably ignores some of the creative aspect of these curves, but the flipside is that the neutral axis stays neutral as a given.

The mixing matrices at each stage are controllable, which makes for some nice creative control on the end results. One can’t super intuitively tie those to any familiar terminology, though, so maybe the best would be to provide presets to roughly match the look of some familiar film + paper.

Things are still pretty bare bones and there’s a lot more to experiment with, but just wanted to say hi here. At least I managed to implement a version if the DIR couplers, ignoring the effects on the neighbourhood of the pixel, because CTL scripts can’t sample the neighbour pixels at all…

Some results so far. Parameters were quite quickly tuned, and these certainly are not as neat as yours. However, I think there’s some nice mojo to these still, a bit of a departure from a certain “digital” look.

[[![20250225_0032](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/d/5d937129c4467a6590578f9c7ab699e124f77df1_2_690x459.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/d/5d937129c4467a6590578f9c7ab699e124f77df1_2_690x459.jpeg)

20250225_00321024×682 123 KB](/uploads/short-url/dlOit1wy9vmKVPgg1PzV7yvaHrr.jpeg?dl=1)

[Dealing with yellow color shift - Play Raw by @raublekick](https://discuss.pixls.us/t/dealing-with-yellow-color-shift/48530)

[[![PXL_20210711_223155650](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/4/1451dbf639f67db71014698b16c78d465ccdb10d_2_690x516.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/4/1451dbf639f67db71014698b16c78d465ccdb10d_2_690x516.jpeg)

PXL_20210711_2231556501024×767 246 KB](/uploads/short-url/2TKVMzGdJRTF6QtsG3sfeyPNzBz.jpeg?dl=1)

[Achieving pastel colors - Play Raw by @nish](https://discuss.pixls.us/t/achieving-pastel-colors/42031)

[[![5D3_9253](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/d/8da4d765ede65f335dce3f037f7e752f77c89739_2_690x460.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/d/8da4d765ede65f335dce3f037f7e752f77c89739_2_690x460.jpeg)

5D3_92531024×683 133 KB](/uploads/short-url/kd2uEtQeP0o8i8ANvItGSvgZRMd.jpeg?dl=1)

[Guys I just discovered LEDs - Play Raw by @ilia3101](https://discuss.pixls.us/t/guys-i-just-discovered-leds/28404)

[[![blue_bar_709](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/3/c3c2e426d5c3046ca5f383118fb55a7a6683a38a_2_690x388.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/3/c3c2e426d5c3046ca5f383118fb55a7a6683a38a_2_690x388.jpeg)

blue_bar_7091024×576 174 KB](/uploads/short-url/rVMES8EQtSUH9X1qhGZPVhsFkxA.jpeg?dl=1)

[GitHub - sobotka/Testing_Imagery/blue_bar_709.exr](https://github.com/sobotka/Testing_Imagery/blob/main/blue_bar_709.exr)

[[![Signature Edits Free Raw Files - Tag @signatureeditsco IMG_0913](https://d2x313g9lpht1q.cloudfront.net/original/3X/9/b/9b64d7d86c4bd78e4b8d910de79d4e85333332cb.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/9/b/9b64d7d86c4bd78e4b8d910de79d4e85333332cb.jpeg)

Signature Edits Free Raw Files - Tag @signatureeditsco IMG_0913683×1024 145 KB](/uploads/short-url/maG3Vzldfh6hPy6ZbC7serSVhEv.jpeg?dl=1)

source: [signatureedits.com](http://signatureedits.com) free raws

Ps. I will create a new thread about this if I ever get to finish the work so that it can be used also by someone else than myself.

---

## #251 **Andrea** (@arctic) · 2025-03-20 20:04

Hey [@flannelhead](/u/flannelhead), that’s very cool! And thanks for the appreciation comment.

> **@flannelhead** (帖子 #250):
> instead of spectral data, it works on tristimulus data in all stages and uses matrices to account for the spectral sensitivites and the dye characteristics.

I think this is a very interesting topic: “how much can we simplify the problem while keeping most of the final style”. It is very cool to see project like yours, where you go very coarse with the bare minimum to simulate the steps, gaining control and ability to drive the simulation with easier parameters.

One drawbacks to use the full data like in `agx-emulsion` is that some of the control is lost, and messing with them can have quite unpredictable results.

One of the question of mine that I would like to experiment with is try to infer “what is the spectral pipeline adding to the mix?”, and if possible if this effect can be simplified and modeled in some way in a tristimulus simulation. Intuitively the spectral simulation is adding something. When the density of a negative increases, the spectrum of the transmitted light through a negative is not simply scaled but bands shifts due to the saturation of the main absorption peaks. But how relevant are these effects for the final look, this is interesting to explore.

> **@flannelhead** (帖子 #250):
> but just wanted to say hi here. At least I managed to implement a version if the DIR couplers, ignoring the effects on the neighbourhood of the pixel, because CTL scripts can’t sample the neighbour pixels at all…

Cool that you managed to simulate the inhibitors from DIR couplers. If you feel like sharing the scripts at any time, it would be interesting to follow your experimentations. I don’t know much about CTL scripts, so it is cool to get to see something different.

The results are promising, indeed!

[![:sunglasses:](https://discuss.pixls.us/images/emoji/apple/sunglasses.png?v=12)](https://discuss.pixls.us/images/emoji/apple/sunglasses.png?v=12)

At the beginning of my experimentations I struggled to see decent colors for quite a while

[![:laughing:](https://discuss.pixls.us/images/emoji/apple/laughing.png?v=12)](https://discuss.pixls.us/images/emoji/apple/laughing.png?v=12)

---

## #252 **Jakob Andrén** (@jandren) · 2025-03-21 14:48

Pretty neat results from only using tristimulus representation! Any magic tricks added for things like clipping out of gamut colors?

For the matrix representation, would it work to define the film and paper basis colors and then just see it as a transformation between the two? So a user would define them in global coordinates and we calculate the relative transform?

Maybe not so surprising coming from me, what curve did you use for the density? Your post inspired me to check how the film and paper density curves compares in the old tone curve tool I made. Here is the result for Kodak Portra 400 and Kodak Endura Premier:

<div class="lightbox-wrapper">[[![Kodak Portra 400 vs sigmoid](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/4/a41ac0d4221f5ade708d2ff9b66195e0c4e6f600_2_690x366.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/4/a41ac0d4221f5ade708d2ff9b66195e0c4e6f600_2_690x366.png)

Kodak Portra 400 vs sigmoid2555×1356 149 KB](/uploads/short-url/npJCFv16CuhiOtW6x9efY0ECakM.png?dl=1)

[[![Kodak Endura Premier vs sigmoid](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/d/2d69728be098e83bd8ba2ee666e0472a8fa515a2_2_690x418.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/d/2d69728be098e83bd8ba2ee666e0472a8fa515a2_2_690x418.png)

Kodak Endura Premier vs sigmoid2282×1383 145 KB](/uploads/short-url/6tJpbKECX3bkh5clI6XeMWMh0e6.png?dl=1)

[[![Film and paper vs sigmoid](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/d/0dc340917e85f54611d238088aca761b03872139_2_690x370.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/d/0dc340917e85f54611d238088aca761b03872139_2_690x370.png)

Film and paper vs sigmoid2370×1274 139 KB](/uploads/short-url/1XKx372k1ju3kUz4gfxkTaa2VlL.png?dl=1)

</div>

I’m pleased to see that the analog film and paper properties can be modeled quite well independently. The formulation used in the sigmoid module is close to the film + paper situation but unfortunatly not exact from what I can see so far. Might be possible to bring it in as a non breaking change but have to look closer at that problem. Add the spectral parts and we would have a pretty significant module upgrade.

---

## #253 **Sakari** (@flannelhead) · 2025-03-21 21:25

> **@arctic** (帖子 #251):
> One of the question of mine that I would like to experiment with is try to infer “what is the spectral pipeline adding to the mix?”, and if possible if this effect can be simplified and modeled in some way in a tristimulus simulation. Intuitively the spectral simulation is adding something. When the density of a negative increases, the spectrum of the transmitted light through a negative is not simply scaled but bands shifts due to the saturation of the main absorption peaks.

Yes indeed, this is very interesting, most probably there are some tradeoffs to be made, and it would be best to make them consciously.

> **@arctic** (帖子 #251):
> If you feel like sharing the scripts at any time, it would be interesting to follow your experimentations.

Yes, I will share at some point for sure!

---

## #254 **Sakari** (@flannelhead) · 2025-03-21 21:47

> **@jandren** (帖子 #252):
> Any magic tricks added for things like clipping out of gamut colors?

No magic tricks played so far. The data is taken in in linear Rec. 709 encoded RGB (supplied by ART) and negative components are just clipped to zero individually. This part will need to have something better, as not all of the usual difficult images (e.g. Red Xmas and Nightclub in Troy’s testing image repo) are treated as well as the demos I posted above.

However, from that point on, things are pretty well controlled. The most important point to take care about is that none of the matrices have negative elements. Think about this: it can never happen that having a greater transmittance in one of the tristimulus components results somehow in less density in some of the paper layers.

> **@jandren** (帖子 #252):
> For the matrix representation, would it work to define the film and paper basis colors and then just see it as a transformation between the two? So a user would define them in global coordinates and we calculate the relative transform?

Hmm, this is an interesting question. So far, the main controls are just rotations and insets of the individual RGB components in various stages of the pipeline. So things are shifted subtly (or not so subtly) in one direction or another, currently I’m adjusting it just by eye and looking at results from Andrea’s spectral simulation. I am not 100 % sure if a colorimetric coordinate approach makes sense here, as the intent is to be closer to the spectral processing.

There are various stages where some kind of spectral projection happens. The pipeline is as follows:

1. Linear Rec.709 RGB in
2. Clip negative lobes to zero
3. Film inset / rotation matrix - this is what would correspond to the film spectral sensitivities
4. Film density curves
5. (DIR couplers)
6. Film density to transmittance
7. Paper inset / rotation matrix. This is where the relationship of the film spectral dye densities and paper spectral sensitivities comes in play.
8. Paper density curves
9. Paper density to reflectance
10. Final rotation matrix - taking in account also the paper dye reflection spectra

At least phases 3, 7 and 10 are where the various spectra can be considered and where creative control can be taken. It would be surely interesting to explore what would be the most user-friendly way to expose that.

> **@jandren** (帖子 #252):
> Maybe not so surprising coming from me, what curve did you use for the density?

Currently the one from [Troy’s repo](https://github.com/sobotka/SB2383-Configuration-Generation/blob/main/sigmoid.py). The current curves are just eyeballed very quickly and should be improved upon.

> **@jandren** (帖子 #252):
> Your post inspired me to check how the film and paper density curves compares in the old tone curve tool I made. Here is the result for Kodak Portra 400 and Kodak Endura Premier

Nice results, it seems the total result is nearly there indeed.

> **@jandren** (帖子 #252):
> The formulation used in the sigmoid module is close to the film + paper situation but unfortunatly not exact from what I can see so far.

Maybe being exact doesn’t matter if one can derive the desired aesthetics from a simpler model.

---

## #255 **jo** (@hanatos) · 2025-03-22 13:11

i have a question about the chemical process. just looked through a few old film scans on my harddrive. what is this:

[![img_0000](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/e/ce361ca817dbfbc87e632cc7628f1dc6312a1e91.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/e/ce361ca817dbfbc87e632cc7628f1dc6312a1e91.jpeg)

the couplers i have thus far *inhibit*, i.e. the negative doesn’t develop so much, i.e. the picture becomes brighter, right? what’s with the black fringes? is that some sort of coupler too? also the radius is really large.

---

## #256 **Andrea** (@arctic) · 2025-03-22 14:15

> **@hanatos** (帖子 #255):
> i have a question about the chemical process. just looked through a few old film scans on my harddrive. what is this:

Interesting. Could you give some context on the image. What are we looking at? What is the scale? How was the negative inverted?

I am pretty sure that there are chemical/diffusion effects that we are not considering. For example, there can be local effects on the concentration of developer, that is depleted by the high density areas, and in my mind would act as inhibition.

The inhibitors released by DIR couplers should create a low density edge on the lower density side and a high density edge on the higher density side (because in this second case it is not as much inhibited as in the middle of a high density area, where all the sides provide inhibitors that diffuse into it).

---

## #257 **jo** (@hanatos) · 2025-03-22 14:33

> **@arctic** (帖子 #256):
> Interesting. Could you give some context on the image. What are we looking at? What is the scale? How was the negative inverted?

*cough* yes. the only thing i know for sure is that image was scanned more than 20 years ago, i think 35mm film.

edit: we see: person diving into probably jerlov water type 1C fluorescent green/cyan/blue ocean.

these images are scanned in uhm, some lab? and 2088 pixels wide. the image here is cropped in height, but not in width (but i inpainted and downscaled it because people on it). i suppose it’s some aggressively colourful consumer film stock but i can’t tell you which. the grain is way sub-pixel, i don’t think i can tell much in terms of inter-pixel correlation at all.

this black fringing happens only for this extra cyan blue water and at edges. can’t necessarily say that it has to be a bright or dark edge, maybe just different layers/colour channels.

> **@arctic** (帖子 #256):
> a low density edge on the lower density side

right that’s the local contrast increase i’m seeing. this particular case in the extreme would cause white fringes on the brighter side of the edge (in positive print).

but yeah, also i’m quite surprised by the large diffusion radius here. my couplers don’t diffuse *that* much, and if i got that right you were indicating that we wouldn’t necessarily expect it to have much spatial influence.

oh btw i also implemented a code path that takes a scaned analog film negative as input and only does the virtual print. it kinda works but needs manual fiddling with the white balance, and i find myself subtracting an elevated black point or applying a curve to the negative before processing for better results.

---

## #258 **Andrea** (@arctic) · 2025-03-22 14:59

> **@hanatos** (帖子 #257):
> we see: person diving into probably jerlov water type 1C fluorescent green/cyan/blue ocean.

Now I see it! Thanks! It is a very large effect indeed.

At the beginning I thought it was some sort of micro detail of a photo.

I would be fun to look at the negative. I wonder if the lab was doing any kind of automatic local contrast adjustment.

> **@hanatos** (帖子 #257):
> oh btw i also implemented a code path that takes a scaned analog film negative as input and only does the virtual print. it kinda works but needs manual fiddling with the white balance, and i find myself subtracting an elevated black point or applying a curve to the negative before processing for better results.

That’s super cool! I had some ideas around that but didn’t have the time to try anything recently. How did you solve the issue of converting the RGB input of the scan into dye densities? Do you bypass that and spectrally upsample directly?

---

## #259 **jo** (@hanatos) · 2025-03-22 15:26

> **@arctic** (帖子 #258):
> I would be fun to look at the negative. I wonder if the lab was doing any kind of automatic local contrast adjustment.

hmm good point! i’ll look around, not sure i have the negative.

> **@arctic** (帖子 #258):
> How did you solve the issue of converting the RGB input of the scan into dye densities? Do you bypass that and spectrally upsample directly?

yes exactly. i interpret the scan as transmittance and upsample that to get approximate spectral power again. on the good side, the upsampling doesn’t work for stuff like collision coefficients/densities, but it’s kinda meaningful for transmittances.

---

## #260 **** (@mikae1) · 2025-03-22 21:30

Hey [@arctic](/u/arctic)! I’m pretty sure you posted a black and white image done with agx-emulsion. Have looked through you activity and can’t find it. It was of a woman. Have I dreamed this up?

---

## #261 **Andrea** (@arctic) · 2025-03-22 22:37

Still no black and white profiles

[![:grin:](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)

 but I hoarded some more BW datasheets, and I will start hacking the pipeline for this soon. I didn’t design the program abstract enough to make these changes easy. I have another dense week at work, but after that hopefully more spare time and brain space to try new things!

[![:star_struck:](https://discuss.pixls.us/images/emoji/apple/star_struck.png?v=12)](https://discuss.pixls.us/images/emoji/apple/star_struck.png?v=12)

If you mean this [Embrace the noise! - #20 by arctic](https://discuss.pixls.us/t/embrace-the-noise/17248/20), it was some early experimentation with adaptive grain, that I never really finished or shared. Conceptually it is not too far from one sub-layer of the grain engine here. It was a simple script, without density curves, I should still have it somewhere.

---

## #262 **** (@mikae1) · 2025-03-23 13:17

> **@arctic** (帖子 #261):
> If you mean this Embrace the noise! - #20 by arctic, it was some early experimentation with adaptive grain, that I never really finished or shared.

Ah, I see! Yeah, that was the post I was thinking of

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

---

## #263 **Nate Weatherly** (@NateWeatherly) · 2025-03-24 17:01

> **@arctic** (帖子 #261):
> Still no black and white profiles but I hoarded some more BW datasheets, and I will start hacking the pipeline for this soon. I didn’t design the program abstract enough to make these changes easy. I have another dense week at work, but after that hopefully more spare time and brain space to try new things!

In case you haven’t come across it yet, this German version of the Xtol Datasheet has Xtol curves for a whole bunch of films, including Ilford, Agfa, and Fuji in addition to Kodak: [https://125px.com/docs/techpubs/kodak/xtolEntwickler.pdf](https://125px.com/docs/techpubs/kodak/xtolEntwickler.pdf)

---

## #264 **Nate Weatherly** (@NateWeatherly) · 2025-03-24 17:26

> **@hanatos** (帖子 #255):
> i have a question about the chemical process. just looked through a few old film scans on my harddrive. what is this:

the couplers i have thus far inhibit, i.e. the negative doesn’t develop so much, i.e. the picture becomes brighter, right? what’s with the black fringes? is that some sort of coupler too? also the radius is really large.

Could it be enlarger/scanner lens diffusion? Or, depending on the scanner, digital processing to increase clarity or tame dynamic range (a la fuji frontier)?

Also, I really need to know… what the heck IS that??? gnawed sweet potato? lumpy hairy nipple?

[![:sweat_smile:](https://discuss.pixls.us/images/emoji/apple/sweat_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/sweat_smile.png?v=12)

---

## #265 **jo** (@hanatos) · 2025-03-25 08:35

> **@NateWeatherly** (帖子 #264):
> Also, I really need to know… what the heck IS that??

chrr since you insist: it’s the skipper diving under the boat to cut a line out of the ship’s propeller which got caught in there and unfortunately, since it’s made of plastic, melted into a neat big clump…

---

## #266 **Andrea** (@arctic) · 2025-03-27 01:11

[@hanatos](/u/hanatos), I wonder if you have any image to show from the direct conversion of negative scans. Anything cool to share? Just very curious

[![:grinning:](https://discuss.pixls.us/images/emoji/apple/grinning.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grinning.png?v=12)

In the meanwhile I added the full Vision3 family to the data.

Here is the updated test table with skin tones:

[[![collage_2025_03_27](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/f/df7964a83793cba9d7fa96ba040e251bf1ffd723_2_390x1000.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/f/df7964a83793cba9d7fa96ba040e251bf1ffd723_2_390x1000.jpeg)

collage_2025_03_271899×4860 705 KB](/uploads/short-url/vSWyHc53rqwyTY49H3UWMOjLxOb.jpeg?dl=1)

The Vision3 family is consistently more neutral than specialized photography film.

I am still thinking a bit about the profile making. I wanna make the the unmixing of the sensitivity a bit more rigorous. Apparently in the measurements of sensitivity of print paper the light source is filtered with something that emulates a neutrally exposed film. I should add this and see if things improve, especially later for the neutral fitting of filters.

Another small investigation done in the weekend is about the 3DLUTs, encoding what is happening in the enlarger and in the scanner. Apparently they are very smooth and thus I reduced the default size of the LUTs to 17x17x17x3, accelerating a little more the calculation.

This is an example of the enlarger 3DLUT for Kodak Gold 200 and Kodak Endura Premier. The color of the curves encodes the amount of input density in the other channels (thus not the x axis).

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/6/263adc7f4a510383df5ddec03099889543ac6835_2_690x669.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/6/263adc7f4a510383df5ddec03099889543ac6835_2_690x669.png)

image705×684 72.7 KB](/uploads/short-url/5scfJ681GUzFy6vaw4ySMqbgy7b.png?dl=1)

The crosstalk is not much because of the masking couplers added in the making of the profiles.

Anyone knows a neat way to visualize/represents these 3D LUTs? I just plotted a few sections taken in every dimension.

---

## #267 **jo** (@hanatos) · 2025-03-28 10:22

wow really nice! i’ll need to rebuild my film stock lut then! at some point maybe the precomputed 3d luts will be interesting for me too to speed up computation a bit. might be interesting for real time raw video.

anyways, i put together a short video processing [this playraw](https://discuss.pixls.us/t/tree-above-stream-digital-film/48707/15):



i’m first processing the digital raw → filmsim + print and then the scanned negative → virtual print. as you can see i needed some of the non-physical paper gamma to make the contrast match better. also since i don’t know the film stock i have to play with the filters quite a bit to arrive at an approximately neutral render (no precomputed data from the fitter).

---

## #268 **Jonathan Bieler** (@jonathanBieler) · 2025-03-28 12:25

Cool, the film is Kodak Gold 200. Also for reference I added the SOOC jpeg in my post, it’s an early morning shot so the light is blueish.

---

## #269 **Nate Weatherly** (@NateWeatherly) · 2025-03-28 15:07

Ah, yes, I’m all too familiar with digging line out of a prop, except in my case it’s usually just a trolling motor and no diving is necessary

[![:sweat_smile:](https://discuss.pixls.us/images/emoji/apple/sweat_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/sweat_smile.png?v=12)

---

## #270 **jo** (@hanatos) · 2025-03-28 19:00

> **@jonathanBieler** (帖子 #268):
> Cool, the film is Kodak Gold 200. Also for reference I added the SOOC jpeg in my post, it’s an early morning shot so the light is blueish.

ah thanks that makes sense. it seems the kodak gold 200 can explain some of the fog/min density i’m seeing. unfortunately the calibration is apparently not absolute. not sure what happens during scanning and whether that might throw off the white point too. if i leave the fitted values for kodak gold and one particular printing paper combination it becomes very blue indeed (sets cyan filter to 0.3 instead of 0.7…0.8 like i did above).

---

## #271 **Revanza Pratamasyah** (@Revanza_Pratamasyah) · 2025-04-13 07:38

> **@arctic** (帖子 #19):
> python agx_emulsion\gui\main.py

Hello, first of all Thank you so much for the effort of making the project!

However, I’m struggling with the installation, could you help me with the installation?

[[![Screenshot (70)](https://d2x313g9lpht1q.cloudfront.net/original/3X/9/3/939d4aee25bb75c70dfa933c316e042f3ec165ae.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/9/3/939d4aee25bb75c70dfa933c316e042f3ec165ae.png)

Screenshot (70)1896×1012 33 KB](/uploads/short-url/l3RbxLytra55kfsCJPktq8PlVKu.png?dl=1)

this is the command that I received.

---

## #272 **Y** (@Y69) · 2025-04-13 09:37

It seems you downloaded the `0.1.0-alpha` release ZIP from February, right? If so then try to use `git clone` the project to get the latest updates.

---

## #274 **Revanza Pratamasyah** (@Revanza_Pratamasyah) · 2025-04-13 10:21

> **@liam_collod** (帖子 #21):
> uv run --python 3.11 --with-requirements requirements.txt --no-project --with-editable . agx_emulsion/gui/main.py

Hi thanks for helping out, I’ve managed to download the latest package using UV, and it automatically opens the GUI. If I want to open the GUI again should I use the same command that download the file, or can I just run the downloaded ones?

Thanks!

---

## #275 **** (@mikae1) · 2025-04-13 10:23

Hi! I wonder where `requirements.txt` has gone in the later versions? I’ve `git clone`d the repo but I can’t find a `requirements.txt` in there and I get `error: File not found: requirements.txt`.

---

## #276 **Revanza Pratamasyah** (@Revanza_Pratamasyah) · 2025-04-13 11:39

Hi, just download the emulsion using UV method by CMD just like on the github. When it’s done it’ll automatically opens the GUI for you to edit the photos in. *Don’t forget to install UV first

However, next time you want to launch the emulsion, you have to run the “main.py” using CMD which command is “uv run main.py”

Which located in “agx_emulsion\gui” but to locate where the full downloaded files is, simply look at the CMD during or after the agx emulsion downloading process.

---

## #277 **Felix Kloss** (@luator) · 2025-04-13 18:28

You can now simply use

<pre data-code-wrap="sh"><code class="lang-sh">uvx --from git+https://github.com/andreavolpato/agx-emulsion.git agx-emulsion
</code></pre>

to run the latest version (see README).

The requirements.txt has been removed as it’s not needed anymore when using uv or pip.

---

## #278 **Andrea** (@arctic) · 2025-04-14 21:46

The requirements were embedded in the `setup.py` and will be resolved automatically. We updated the installation guide in the repo, too.

[![:wink:](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)

---

## #279 **** (@mikae1) · 2025-04-16 06:06

Thanks! Eventually noticed the guide was updated.

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 Seems installation automatically goes to `~/.cache/uv/` now?

---

## #280 **Felix Kloss** (@luator) · 2025-04-16 11:16

Yes, when you use uvx, it installs to the cache directory, so it will automatically download stuff the first time and then use the cached version (unless there is an update on the repo).

But you can also pip-install to a manually created virtual environment if you prefer that.

---

## #281 **David Otero Navarro** (@David_Otero_Navarro) · 2025-04-25 09:27

This is brilliant! I was thinking of doing something similar to invert my color negative scans, so you just saved me a ton ow work

[![:joy:](https://discuss.pixls.us/images/emoji/apple/joy.png?v=12)](https://discuss.pixls.us/images/emoji/apple/joy.png?v=12)

.

---

## #282 **Steven** (@123sg) · 2025-04-30 11:56

Hi,

I’ve been so busy I have had very little time to spend on this. I’m having time off now for health reasons so have some time to play again.

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

When trying to run on Windows using uv as per the readme I get this error:

```
(base) PS C:\Users\SG3> uvx --from git+https://github.com/andreavolpato/agx-emulsion.git agx-emulsion
 Updating https://github.com/andreavolpato/agx-emulsion.git (HEAD) x Failed to resolve `--with` requirement
 `-> Git operation failed
(base) PS C:\Users\SG3>

```

Am I doing something daft? The bit about failed to resolve --with requirement (scroll to see it) is puzzling me.

I had previously installed via pip and conda but wanted try the uv route. I’m a bit clueless on package managers as is probably obvious…

---

## #283 **Benjamin** (@piratenpanda) · 2025-04-30 13:00

Which uv version are you using?

---

## #284 **Steven** (@123sg) · 2025-04-30 13:13

`uv 0.7.1 (90f46f89a 2025-04-30)`

Running in Powershell btw

---

## #285 **Sébastien Guyader** (@sguyader) · 2025-05-05 12:45

I see that you’re running `uv` within what is maybe a conda environment, did you install `uv` from conda?

---

## #286 **** (@mino) · 2025-05-14 18:24

Fascinating project! I wanted to dip my toes into the emulsion as well but am having trouble installing.

running fedora 41 inside distrobox with installed dependencies (as far as I could tell): python, git, gcc

trying `uvx --from git+https://github.com/andreavolpato/agx-emulsion.git agx-emulsion` fails because it apparently cant build vispy ([output](https://pastebin.com/bm9CJ9Md))

using pip yields a seemingly similar issue ([output](https://pastebin.com/e5jphLYe))

Can someone give me a hint how to further troubleshoot or what I am missing?

---

## #287 **Todd Prior** (@priort) · 2025-05-14 18:45

You could maybe use the info here from Steps 1 and 2…the third step is specific to an implementation in ART but the first two might help…

[https://art.pixls.us/AgXEmulsionLutHowto](https://art.pixls.us/AgXEmulsionLutHowto)

---

## #288 **** (@tankist02) · 2025-05-14 21:33

I installed on F41 (though the real thing, without distrobox) using the pip and conda methods, both worked.

---

## #289 **** (@evilgenivs) · 2025-05-15 02:28

I really don’t like this software. /sarcasm Because I finally got a look I want out of darktable (after years) and on the same day I find this… insane insane insane film emulation wow. I can’t wait for more man!

---

## #290 **** (@mino) · 2025-05-15 13:32

In case someone searches for this. I solved it, apparently I was missing python3-devel and PyQt5 as dependencies. To run this inside a Fedora 41 distrobox I installed `git` `gcc` `python` `uv` `python3-devel` and `PyQt5` and was able to install agx-emulsion via the “pip-route” as well as via `uv`.

This is way to much fun. Awesome and utterly fascinating work [@arctic](/u/arctic)!

[[![250412_090048_DSC02448-portra160](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/b/8b271977880f0e55ecdaa940b909162e68d15fad_2_665x1000.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/b/8b271977880f0e55ecdaa940b909162e68d15fad_2_665x1000.jpeg)

250412_090048_DSC02448-portra1603472×5219 1.56 MB](/uploads/short-url/jR08AWljQMnWdMdH7E5dpSddlJb.jpeg?dl=1)

---

## #291 **Billal** (@Billal) · 2025-05-25 12:22

When I did all the steps in the documentation of Art page it sais the lut is invalid

I managed to launch Napari, but nothig seems to work with the test image

I hope someone could help !

---

## #292 **Billal** (@Billal) · 2025-05-25 12:36

[[![Capture](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/e/5ea4ab7274fae91beca8d5c983ac0149ef2256da_2_690x388.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/e/5ea4ab7274fae91beca8d5c983ac0149ef2256da_2_690x388.png)

Capture1364×768 227 KB](/uploads/short-url/dvfGuUiO5kggPCa3PZBQSz24Uwq.png?dl=1)

Take a look at this image; when I change he settings nothing seems to work !

---

## #293 **Billal** (@Billal) · 2025-05-25 15:39

[[![Capture &](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/8/c865f5e6aff53b2a5d2c51743194712091b672ac_2_690x375.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/8/c865f5e6aff53b2a5d2c51743194712091b672ac_2_690x375.png)

Capture &1356×737 389 KB](/uploads/short-url/sANWv3zV0bP1GirZiMSGyEYSkUY.png?dl=1)

Look at the message I get when I turn on the film simulation and the same message in the color correction tab

---

## #294 **Alberto** (@agriggio) · 2025-05-25 16:01

Hi,

If the standalone app doesn’t work, it means something went wrong somewhere in the installation. Until you figure that out, there’s nothing that can be done on the art side I’m afraid, sorry.

---

## #295 **** (@mino) · 2025-05-25 19:44

cant speak to ART but in napari you have to probably scroll down in the right panel and “run” the emulation!

---

## #296 **Steven** (@123sg) · 2025-05-25 20:21

> **@mino** (帖子 #295):
> scroll down

This - on my win 11 machine I also have to do a bit of drag and drop module rearranging to get the run button visible

---

## #297 **Billal** (@Billal) · 2025-05-25 20:30

I’ll try that, thanks

---

## #298 **Billal** (@Billal) · 2025-05-25 22:55

[[![simulation result1](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/3/f396d308568e5b0b593b064e032766f195b25db6_2_664x1000.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/3/f396d308568e5b0b593b064e032766f195b25db6_2_664x1000.jpeg)

simulation result11993×3000 8.11 MB](/uploads/short-url/yKTaedKObqNbEidKgJoKI8SAuNw.jpeg?dl=1)

I managed to try an image of mine and I have to say that I have never seen something that even close to this software… just mind blowing. The only downside is the processing power that it requires and the difficulty of using it in general, other than that it’s fascinating.

A major thanks to [@arctic](/u/arctic).

---

## #299 **Revanza Pratamasyah** (@Revanza_Pratamasyah) · 2025-05-28 03:51

Hello everyone, I was wondering is it possible to use the software only for the grain emulation? I’ve been tinkering with the settings and couldn’t find a way to disable the “color profile”.

---

## #300 **None** (@lanidor) · 2025-05-28 15:48

I stumbled across this project and have to give kudos to [@arctic](/u/arctic) for making it happen. I’ve been shooting film for the past 3 years, and none of the plugins come this close to the film look (Yedlin is also pretty close, but his code is not publicly available, and you need Nuke to run it).

A small tip I’d like to share, adding a narrow black frame in Darktable acts like a film rebate, which should be the darkest point during inversion. Also, if Napari’s background is set to white, it makes it easier to evaluate contrast and white balance.

Would it be too much of a hassle to include Agfa films? I love the look they had, muted colors with dense primaries, too bad they stopped production (NC500 should be similar, but it’s too grainy).

Thanks again!

[AGFA.F-AF-E5.pdf](/uploads/short-url/uNSea7tB0kBvfJPE99CxJUDVkY6.pdf) (163.7 KB)

---

## #301 **John Apolozan** (@JApolozan) · 2025-06-02 02:59

Hi Andrea (arctic),

I want to start by thanking you for creating this project. While my Python is extremely rusty (last time I touched it, Barack Obama was still in office) I feel that you have created an extremely close and elegant emulation to the real thing. The closest thing that I tested that gave somewhat similar results was Filmulator.

I have compared digitizations of the Fuji 400 (X-Tra) to the same frames taken on my D810 at the time. While I will not post the images here (portraits of a close friend), I can say that running the ART integration agx-emulsion and starting from the default values is very close. To add some flavor, I compared both the fancy Noritsu scans (minilab) and my DSLR digitizations. While the colors obviously differed a little (proprietary profiles and weird piece-wise contrast curves) the ballpark was the same, the look and feel was there.

As a side-note, I also compared Portra 400 prints on matte paper to results from the emulation and they were really close, granted I didn’t have the exact frame for reference, so I could only trust my eyes.

I have scans of colorcheckers SG and Passport targets at different exposure levels, under D50, StdA and Flash illuminantion, if you feel they might be useful for a few stocks: Portra 400, Fuji 400, Pro Image 100 and Ektar 100.

Thank you again for the work done on this project and look forward to developments to the code.

Best Regards,

John

---

## #302 **WG** (@BPH3647) · 2025-06-02 18:03

Does anyone have any tips for verifying the Napari launched version on MacOS is running correctly? I’ve gotten familiar with it over the past couple weeks and coming from darkroom printing its pretty intuitive but I’ve had the nagging feeling its not compiled correctly.

I downloaded one of the example images [@arctic](/u/arctic) used and matched it to his Darktable output but when I use the same settings in Agx it seems impossible to match the example output.

A screenshot dump of my settings and comparisons below.

- My .NEF conversion vs. the jpeg [@arctic](/u/arctic) uploaded
 [[![DT_Screen-01](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/5/a59bb3d18d34257c64909af542c2574666297349_2_690x920.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/5/a59bb3d18d34257c64909af542c2574666297349_2_690x920.jpeg)
 DT_Screen-013000×4000 1.17 MB](/uploads/short-url/nD2n9MsTAgapXFZbMWKrgBoNLrH.jpeg?dl=1)
- V1 series of settings used in Agx | Notes below
 [[![Agx_Screen-01](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/e/7e12e5f0f0f2a4d858730e41327c8d4046180127_2_690x687.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/e/7e12e5f0f0f2a4d858730e41327c8d4046180127_2_690x687.jpeg)
 Agx_Screen-013000×2989 626 KB](/uploads/short-url/hZiEkwkV8ut4SpO69y2LYRbHnzp.jpeg?dl=1)
- Resulting jpeg compared with [@arctic](/u/arctic) jpeg
 [[![PS_Screen-01](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/5/05696f1622508fd5bdd8fedcc26f92ca522bd39e_2_604x1000.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/5/05696f1622508fd5bdd8fedcc26f92ca522bd39e_2_604x1000.jpeg)
 PS_Screen-013000×4964 1.07 MB](/uploads/short-url/LShgApygf2Qi82IO5ZgeQ5ByZE.jpeg?dl=1)

As far as the settings used in darktable: I went through this and the other thread to try to find as much info as to the settings used for the initial Raw conversion export. I’ve tried many combinations aside from these in respect to color profiles. I still end up at a result that doesn’t match. A sRGB processed file in photoshop matches the example JPEG downloaded from the post.

The settings in Agx that give me pause are the ‘cctf de/encoding’, though no amount of check/uncheck combinations get me closer.

I’m pretty stumped! The resulting contrast and clipping is a big jump from what I think I should be expecting.

Is it possible that loading the app straight from Github could be the source? I’ve only had a few hours to try to figure out the cuda approach but I’m so out of my wheelhouse that I consider myself lucky I got the terminal aspect to actually load. I would try it with the ART program but, again, I have no idea how to even install it on a Mac.

Apologies for this wall of text!

---

## #303 **jo** (@hanatos) · 2025-06-02 18:22

did you import the jpg into agx-emulsion? you set the input colour space to bt2020 and the screenshot looks like it’s actually sRGB. not sure about the cctf (you should check this box if the input is in fact sRGB/jpg, but is it?).

---

## #304 **WG** (@BPH3647) · 2025-06-02 21:31

> **@priort** (帖子 #287):
> Spectral film simulations in ART with agx-emulsion | ART raw image processor

Hey [@hanatos](/u/hanatos)

I’m exporting a 16bit Tiff from darktable with the Linear Rec2020 profile and loading that into agx. The JPEG is me verifying the histogram is similar to what [@arctic](/u/arctic) had done with their raw conversion.

---

## #305 **John Apolozan** (@JApolozan) · 2025-06-03 17:13

I’ve compared a scan of Portra 400 metered for ISO 400 and on digital on the same equivalent exposure, with agx-emulsion applied with default settings (.xmp and .arp attached for reference).

[[![Dslr0567](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/7/07a23ac1326cdd7a4551e8330d4f4cd499e1fab7_2_690x238.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/7/07a23ac1326cdd7a4551e8330d4f4cd499e1fab7_2_690x238.jpeg)

Dslr05672047×707 387 KB](/uploads/short-url/15wUSxZjlrIIlItOnOCIjbamSr5.jpeg?dl=1)

[Dslr0567.NEF.xmp](/uploads/short-url/9oM85779j2wAw2i54woWFb3NRG2.xmp) (11.7 KB)

[[![_8105001](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/2/725ee8f466a3a29b57cc2ffa31596bf67a0e521b_2_690x211.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/2/725ee8f466a3a29b57cc2ffa31596bf67a0e521b_2_690x211.jpeg)

_81050012048×629 271 KB](/uploads/short-url/gjLM4lpcspkk2f0Zn4SgSxDQSJJ.jpeg?dl=1)

[_8105001.jpg.out.arp](/uploads/short-url/rC581vJlhj6sInOvztVCcpzBYmT.arp) (11.5 KB)

While not identical, the look & feel is there. Most likely the print properties for the negative could be tweaked more to look like the agx settings or the other way around.

Thanks again for creating this amazing tool and integrating it in ART.

Best,

John

---

## #306 **jo** (@hanatos) · 2025-06-04 07:26

wow cool! you wouldn’t be able to share the raw/scan/input images here too? something about the luminance/tone response in the blacks that looks different enough so i would like to play with the data

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

---

## #307 **John Apolozan** (@JApolozan) · 2025-06-04 18:45

Hi jo,

Hopefully this works. Pardon my messy living room/photographic lab

[![:smiley:](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)

Shots taken minutes apart, same lighting, lens, aperture and metering. Lens used at capture was a Nikon 105mm f/2.5, digitized with a Nikon Micro-NIKKOR 60mm AF-S G. Additional frame with film rebate for orange mask correction.

[_8105001.NEF](/uploads/short-url/r6IcGPQBZcs8Z5wKj2hyoQoNGrb.NEF) (39.2 MB)

[Dslr0567.NEF](/uploads/short-url/3MyCujwekVjeyhCltt4zx6ujPGU.NEF) (48.8 MB)

[Dslr0568.NEF](/uploads/short-url/9n5fhVBwziyNU0dh0P2rVme037y.NEF) (37.1 MB)

---

## #308 **MrWhoMan** (@Yuri_Andronachi) · 2025-07-01 13:35

This is very curios.

Can someone explain in what state should be input image. Assuming I have a RAW or ARW?

Should it be less contrasty or not manipulated at all? Do I need to prepare it somehow?

---

## #309 **Benjamin** (@piratenpanda) · 2025-07-01 13:51

I’m exporting my edited raws to 32bit exr with linear ProRec colorspace. Works well, although the initial render is off and one need to press run first to get a proper rendering.

---

## #310 **MrWhoMan** (@Yuri_Andronachi) · 2025-07-01 13:58

Thank you. What software are you using to export it to exr?

---

## #311 **Benjamin** (@piratenpanda) · 2025-07-01 14:03

darktable

---

## #312 **** (@mikae1) · 2025-07-01 18:20

> **@Yuri_Andronachi** (帖子 #308):
> Can someone explain in what state should be input image. Assuming I have a RAW or ARW? Should it be less contrasty or not manipulated at all? Do I need to prepare it somehow?

This is how I’ve used it:

1. darktable modules (no tone mapper, i.e. no sigmoid, filmic rgb or base curve)
 [[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/7/7/77aaffb9408f8326126fd05d4b614ffafb7626ef.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/7/7/77aaffb9408f8326126fd05d4b614ffafb7626ef.png)
 image497×721 44.6 KB](/uploads/short-url/h4Dbjsj8bitUwbrEcBeXRi9uEd9.png?dl=1)
2. darktable export
 [[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/6/9/6943a6251a2da324fe6551570a30b1c84e0ee415.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/6/9/6943a6251a2da324fe6551570a30b1c84e0ee415.png)
 image325×490 26.9 KB](/uploads/short-url/f1d4rGDYRsHlJPGXJ7nB16uNr5r.png?dl=1)
3. agx-emulsion input settings
 [[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/8/5/856ab36445f12608e3b77cfac0e942d181a121f9.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/8/5/856ab36445f12608e3b77cfac0e942d181a121f9.png)
 image564×333 24.9 KB](/uploads/short-url/j2g6KuHmVETLfoCGjv1SEGOZW8F.png?dl=1)

---

## #313 **nosle** (@nosle) · 2025-07-06 16:15

Your comparison confirms my experience. I struggle to reduce the “punch” of the digital simulation so that it matches what I’m used to with analogue film.

If anyone figures out how which settings mute and reduce contrast to approximate scanned film it would be great to hear some tips.

---

## #314 **jo** (@hanatos) · 2025-07-07 07:24

the film response is not linear, so you can play with exposure to put your image signal into a range where the blacks are crushed or lifted up. here i reduced exposure *before* application of the film simulation, essentially underexposing by 4 stops, and then compensated via paper print exposure (`ev paper` in the screenshot):

[[![2025-07-07-091536_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/a/fad9c45df3081035bd9b15f64c7920868d322e54_2_690x391.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/a/fad9c45df3081035bd9b15f64c7920868d322e54_2_690x391.png)

2025-07-07-091536_hyprshot2484×1410 922 KB](/uploads/short-url/zN7VKeKIB3ISAqqMQFi98UaA1SY.png?dl=1)

for reference, this is the image with default settings right after applying the filmsim preset:

[[![2025-07-07-091543_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/c/4c0d1e7109426eb00f8076e878f3a7969033f76e_2_690x391.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/c/4c0d1e7109426eb00f8076e878f3a7969033f76e_2_690x391.png)

2025-07-07-091543_hyprshot2484×1410 1.08 MB](/uploads/short-url/aQMotYjMmqUBi1bmHC8efVwmFIO.png?dl=1)

not sure that’s what you’re asking?

---

## #315 **Alberto** (@agriggio) · 2025-07-07 08:14

> **@hanatos** (帖子 #314):
> not sure that’s what you’re asking?

You can also play with “print gamma” to reduce the contrast at output. Maybe that’s what is meant by [@nosle](/u/nosle) ?

---

## #316 **jo** (@hanatos) · 2025-07-07 08:51

right. i didn’t want to advertise gamma since it’s a bit of a non-physical (though useful) option.

at the end of the day there’s still the `min density` in the film stock profile which might not match the footage accurately. before changing the profiles i’d certainly evaluate all options we have in our “secondary” softwares.

---

## #317 **nosle** (@nosle) · 2025-07-07 10:35

Thanks for the tips [@hanatos](/u/hanatos) , [@agriggio](/u/agriggio) I’ve done some quick tests and it’s in the right direction.

---

## #318 **** (@mino) · 2025-07-07 12:23

Is that agx-emulsion in vkdt?

---

## #319 **jo** (@hanatos) · 2025-07-07 12:39

yis. this was integrated for the longest time now… which reminds me i should really make a release. running out of excuses what to finish/merge before 1.0.

---

## #320 **** (@niklasiivari) · 2025-07-07 16:11

Hi, just curious, are there plans to implement the couple missing things from agx-emulsion to vkdt? I am mainly interested in halation, and perhaps print preflash.

Obviously no kind of pressure for this from my part, I have been very happy with the results the filmsim module provides, and this is just something I am kind of sometimes longing for

[![:sweat_smile:](https://discuss.pixls.us/images/emoji/apple/sweat_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/sweat_smile.png?v=12)

.

Another thing I have noticed is, that the magenta and yellow filters have a very different effect depending on which film stock is used, for example, with portra 800, a -1 magenta filter tuning makes a very strong effect, while with portra 400, the effect is much more subtle, and sometimes not even enough to achieve a neutral palette without additional white balance tweaks in the colour module.

---

## #321 **jo** (@hanatos) · 2025-07-08 08:05

ah good point. halation definitely yes. the preflash i forgot about since i’m a bit ignorant to this process. what effects would you achieve with it?

the filters are spectral filters and the film has spectral response… so clearly same filter with different stock will have different overlap and thus show an effect of different strength.

fwiw the fine tuning sliders can be set to overdrive by just typing numbers (click on the number not the slider). or just use the three auto-matched cyan/magenta/yellow sliders (non fine-tune), these will have bigger impact. white balancing is definitely something i struggle with most when using filmsim.

---

## #322 **** (@niklasiivari) · 2025-07-08 08:48

Honestly, the purpose of pre-flashing can probably be achieved with just adjusting the film exposure - paper exposure balance, since it is meant for preserving highlight detail. It seems increasing the negative exposure helps with that nicely!

So, wouldn’t put much priority to this one, I am totally fine even without.

And thanks for the explanation about the filters, are you set on hiding the non-fine-tune sliders from the gui, might be useful to have them visible in some cases?

---

## #323 **jo** (@hanatos) · 2025-07-08 11:18

> **@niklasiivari** (帖子 #322):
> are you set on hiding the non-fine-tune sliders from the gui, might be useful to have them visible in some cases?

hmm i was hoping to reduce the agonising amount of ui elements. maybe a spot wb tool would remove the need to play with the filters? or a more compact widget specifically for these filter weights? have to think about it. in the mean time, fwiw, here is a patch to un-hide the filters whenever paper printing is involved:

<pre data-code-wrap="diff"><code class="lang-diff">--- a/src/pipe/modules/filmsim/params.ui
+++ b/src/pipe/modules/filmsim/params.ui
@@ -17,7 +17,7 @@ size:slider:0.5:2.0
 uniform:slider:0:1.0
 group:process:0
 enlarge:combo:1x resolution:2x resolution:4x resolution
-group:process:2
+group:process:101
 filter c:slider:0:1
 filter m:slider:0:1
 filter y:slider:0:1
</code></pre>

---

## #324 **** (@niklasiivari) · 2025-07-08 12:52

A wb tool might certainly be useful in many cases, since setting web before the filmsim in the colour module often delivers quite strange results. I think I am fine with the fine tune sliders too, most of the time they are enough and when not, setting the number outside the range of the slider should suffice.

---

## #325 **jo** (@hanatos) · 2025-07-10 17:42

now with halation in master. doesn’t exactly help reduce options:

[[![2025-07-10-194126_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/6/8617b3102721a73478c585dd98f3f51115119fd0_2_690x388.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/6/8617b3102721a73478c585dd98f3f51115119fd0_2_690x388.png)

2025-07-10-194126_hyprshot2880×1620 1.48 MB](/uploads/short-url/j8eKVyTZAtKFnLbKx3zllCLj59S.png?dl=1)

---

## #326 **** (@niklasiivari) · 2025-07-10 19:50

> **@hanatos** (帖子 #325):
> now with halation in master.

Awesome!!

And yeah, not-so-important stuff should probably remain hidden to keep it looking somewhat clean.

---

## #327 **** (@niklasiivari) · 2025-07-18 11:52

It is pretty interesting what a big difference halation makes on the effect of couplers. I was playing with the recent playraw submission ([link](https://discuss.pixls.us/t/how-would-you-edit-this-photo/51197)), and this is filmsim in vkdt, fujifilm 400h and kodak 2393, couplers set to 1 and default amount of halation, and then with halation off:

[[![Screenshot 2025-07-18 144242](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/e/fe56df4d8c125b58ca51f4312f82359c612aecd1_2_690x512.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/e/fe56df4d8c125b58ca51f4312f82359c612aecd1_2_690x512.png)

Screenshot 2025-07-18 1442422126×1579 3.84 MB](/uploads/short-url/AhZoPtMW9gKdnkF9tOh57gg8HxD.png?dl=1)

[[![Screenshot 2025-07-18 144303](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/5/35b6fb37aa9f49112f143c7032ca098d716797b9_2_690x509.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/5/35b6fb37aa9f49112f143c7032ca098d716797b9_2_690x509.png)

Screenshot 2025-07-18 1443032129×1572 4.07 MB](/uploads/short-url/7Fblb6OOozrg79ix4cE24eoJrRv.png?dl=1)

As we can see, when halation is enabled, couplers have a much more natural looking effect with increased saturation but less of the very obvious haloing around edges with high contrast.

---

## #328 **jo** (@hanatos) · 2025-07-18 12:16

interesting, thanks for this observation.

i’m not entirely sure which way would be the most physical to apply couplers and halation… in particular which one is applied first? also i increased the radius of the coupler support a bit as compared to the original agx-emulsion (see discussion about photographic reference above where a particular image showed much larger halo regions).

also the kodak 2393 paper is experimental as far as i understand.

---

## #329 **** (@niklasiivari) · 2025-07-18 12:26

[edit] was talking some nonsense, I think halation should happen first, as it happens during exposure, and couplers when developing, right?

And yeah, a coupler amount of 1.0 is already quite extreme, but the haloing has been bothering me with some particular images at the 0.25 range too, so I see this as a welcome effect of halation (in addition to the fact that halation looks great).

And referring to the last point, I went and tested other film-paper combos, and it seems the difference and effect is the same regardless of which are used!

Anyways, to me halation makes it look better, no idea about the physical accuracy

[![:smiley:](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)

---

## #330 **** (@Aaron_b) · 2025-08-15 18:32

Hi, I have been seeing some of your ‘play-raw’ examples and its really cool to see the final result.

I too have been working on my own film simulation. It’s interesting how we came up with different solutions to similar problems. I started with negative film but I got hung-up on trying to simulate a scanning process. More recently, I completed a simulation of reversal film (ektachrome) that I am very happy with. I’m not planning to open-source it but I may share a few details here or via message if you’re interested.

Perhaps I will revisit my negative attempt soon with some new ideas.

---

## #331 **Tanishq Dubey** (@dubey) · 2025-09-02 20:03

Hi! Firstly, thank you for this treasure trove of information!

I’ve been working on my own version of a film simulation and have recently gotten to the point of having a series of photographs that I have taken digitally and on film. (Of the following images, the first is film, second is digital – these are inverted using Darktable with no other corrections)

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/f/1f1597ca70c2ed432ff50f462f316beb4a35edc5_2_332x500.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/f/1f1597ca70c2ed432ff50f462f316beb4a35edc5_2_332x500.jpeg)

image3862×5812 9.19 MB](/uploads/short-url/4qZ3YTyPfbNTDn7zN841yLwjJ6l.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/5/650a447e3ff2c95cef07090c6809813bd0def362_2_333x500.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/5/650a447e3ff2c95cef07090c6809813bd0def362_2_333x500.jpeg)

image1007×1511 610 KB](/uploads/short-url/epQdNQ12XGtWczWdlL0t8QpmXvk.jpeg?dl=1)

I’ve found that when not simulating a scanning process or print process, stocks like Portra 400 have a very flat look and strong teal/blue tint. I’ve been able to replicate this with my scanning (as seen in the images attached) but I’m wondering how scanning labs end up with a totally different look:

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/f/5f3593dfba2dfda470192081dc16859f396fdf75_2_336x500.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/f/5f3593dfba2dfda470192081dc16859f396fdf75_2_336x500.jpeg)

image1440×2142 837 KB](/uploads/short-url/dAg9fGjj6Iz2k5q1KZCp9SUw3Rj.jpeg?dl=1)

Is it really just scanning profiles that are adjusting images this much? I feel like with my simulated image matching the color my at home scan my simulation process is correct, but I would like to get closer to what the lab provides. Any tips anyone?

---

## #332 **Jimmy Qiu** (@Jimmy_Qiu) · 2025-09-03 17:34

Negative film is designed to be printed, not scanned with a regular digital camera. Think of print paper like an animal that can only see certain wavelengths of light. So, when you look at a negative through your camera, of course it’s not going to look right. Lab scanners are built with spectral sensitivities similar to print paper, so the results come out closer to what you’d see in an actual print. If you just invert a negative on a digital scan, you’ll end up with a misinterpreted image, that’s not what Kodak intended.

---

## #333 **István Kovács** (@kofa) · 2025-09-04 10:48

Did you use *negadoctor*? That can take care of the red/orange film base, which likely gives you the blue/green shift after inverting the image.

<aside class="onebox allowlistedgeneric" data-onebox-src="https://darktable-org.github.io/dtdocs/en/module-reference/processing-modules/negadoctor/">
 <header class="source">

 [darktable user manual](https://darktable-org.github.io/dtdocs/en/module-reference/processing-modules/negadoctor/)
 </header>

 <article class="onebox-body">


### [negadoctor](https://darktable-org.github.io/dtdocs/en/module-reference/processing-modules/negadoctor/)


Process scanned film negatives.
You can obtain an image of a negative using a film scanner, or by photographing it against a white light (e.g. a light table or computer monitor) or off-camera flash.
🔗preparation If the image of the negative was...

 </article>









</aside>

 [[![图片397](https://d2x313g9lpht1q.cloudfront.net/original/3X/f/2/f2f0514e9a48be55db958a6442bce1c749cad028.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/f/2/f2f0514e9a48be55db958a6442bce1c749cad028.jpeg)](https://www.youtube.com/watch?v=DiNlHBZE888)

Or is the point that you want to do everything yourself, to learn and/or to improve the process?

---

## #334 **Benjamin** (@piratenpanda) · 2025-09-13 09:33

Really works nicely when paired with an old lens like this KMZ Helios 58 mm f2

<div class="lightbox-wrapper">[[![helios1_small](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/0/10163142c5ed51d7ea8f155f23866d0f74919c26_2_666x1000.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/0/10163142c5ed51d7ea8f155f23866d0f74919c26_2_666x1000.jpeg)

helios1_small800×1200 193 KB](/uploads/short-url/2ijbzcW5zSNbmU8s6y29HyAkGwu.jpeg?dl=1)

[[![helios2_small](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/2/f265b38871604d0d3976d67191ea4a9dca67904a_2_690x459.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/2/f265b38871604d0d3976d67191ea4a9dca67904a_2_690x459.jpeg)

helios2_small1200×800 137 KB](/uploads/short-url/yAlroAuTApak9wM4WJgzwgHw8Ns.jpeg?dl=1)

[[![helios3_small](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/c/9cb9cab9cb5be2ec0353f459227c93c5880f5b5f_2_666x1000.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/c/9cb9cab9cb5be2ec0353f459227c93c5880f5b5f_2_666x1000.jpeg)

helios3_small800×1200 139 KB](/uploads/short-url/mmsxE7k2q7Xuet6FLvv7BDuXSUf.jpeg?dl=1)

</div>

---

## #335 **** (@Thomsen) · 2025-09-25 10:23

Hello! I’ve been searching wide and far for a good film emulation for stills, and this truly looks like a hidden gem! I’ve worked as a colorist in Davinci Resolve, but have no experience with the RAW-editors mentioned here.

Managed to install the 0.1.0 version through python and tried to read through this megathread, but excuse me if some of these questions have already been answered:

Which app is most suitable and fully featured for this workflow? (VKDT, Darktable, ART) - for colours, halation, grain etc.

I see some of the programmes use LUTS, which in the video world often equals worse image quality and compressed colour data - and luts doesn’t transfer grain, hallation etc. Is there a difference between the python versions processing and the LUT-based processing of the other programmes?

Is there a planned 1.0 release and does it make sense to wait for that?

---

## #336 **jo** (@hanatos) · 2025-09-25 10:48

> **@Thomsen** (帖子 #335):
> Which app is most suitable and fully featured for this workflow? (VKDT, Darktable, ART) - for colours, halation, grain etc.

i can only really speak for vkdt, which implements most of the python original quite faithfully, but with some differences. it supports processing of positive raws, scans of negatives, multi-layer grain, halation, and DIR couplers, though not with a pixel-identical implementation. vkdt implements the algorithms on GPU, which makes it easier to wait for the result (much faster).

darktable does not implement any of this, though there is something called “AgX” (as opposed to “agx emulsion”), which is troy’s sophisticated tonemapping engine and not based on film simulation or spectral input.

ART implements something that is similar/equivalent to a LUT approach, it does not transfer grain, halation, or DIR couplers.

(you maintainers correct me if that information is outdated or plain wrong ;))

> **@Thomsen** (帖子 #335):
> Is there a difference between the python versions processing and the LUT-based processing of the other programmes?

yes, see above. IIRC Art uses some per-pixel external script. i don’t know whether that first goes through a discretised/quantised LUT or whether it would at least avoid these kinds of artifacts.

> **@Thomsen** (帖子 #335):
> Is there a planned 1.0 release and does it make sense to wait for that?

i know i have a plan for vkdt 1.0, can’t speak for *agx emulsion*. since this is open source… i don’t think waiting for 1.0 makes much sense.

---

## #337 **** (@Thomsen) · 2025-09-25 16:46

I’ve tested out some old photos in VKDT now. Easily the best colors and texture I’ve gotten without any editing.

A question about halation: The highlights look great and bloom in a nice manner, but the halation seems to affect the midtones more than I normally see in analogue film - decreasing the midtone contrast quite a lot. Is this intended or am I missing some setting? (Just using the node preset as it is).

---

## #338 **nosle** (@nosle) · 2025-09-25 19:58

I’ve been testing some of the old images from this thread. I have to say both vkdt and agx now create images that don’t look much like the samples when following the recipes stated. Generally speaking the results are more “unnatural” than the original results. As if the effect was stronger now.

What are you seeing? Have i lost my mojo or have the developments changed the results that much?

---

## #339 **Benjamin** (@piratenpanda) · 2025-09-26 10:27

or with a Super Takumar 50 1.4:
[[![rose_takumar_small](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/b/6bd1f4601f324d6c576f45149f6948c8aac8b76b_2_668x1000.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/b/6bd1f4601f324d6c576f45149f6948c8aac8b76b_2_668x1000.jpeg)

rose_takumar_small1003×1500 259 KB](/uploads/short-url/fnOUJarKA3nQLUkDfnD8OvJYA1d.jpeg?dl=1)

---

## #340 **jo** (@hanatos) · 2025-09-26 11:42

> **@Thomsen** (帖子 #337):
> but the halation seems to affect the midtones more than I normally see in analogue film

hmm can you give an example? i mean i just implemented the convolution with the default weights. if it’s just a matter of changing these values, i can update the default.

> **@nosle** (帖子 #338):
> Have i lost my mojo or have the developments changed the results that much?

i’m not aware of any such changes. the one thing i know we experimented with is the auto-white balance when exposing the paper. you can always tune manually i suppose.

---

## #341 **nosle** (@nosle) · 2025-09-26 11:51

I’m seeing a similar look with the agx app so it’s either me or changes to both apps since the initial versions. Will show examples when I find the time. My greens are basically brown/yellow with portra and from my film experience I expect a different look where greens turn rather dark and kind of blueish?

---

## #342 **** (@Thomsen) · 2025-09-26 11:52

> hmm can you give an example? i mean i just implemented the convolution with the default weights. if it’s just a matter of changing these values, i can update the default.

Area with highlights and contrasts **without** halation:

[[![Highlights w o halation](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/d/2d60dfe76f4e9062070ae3887960bce3fb15eb39_2_345x296.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/d/2d60dfe76f4e9062070ae3887960bce3fb15eb39_2_345x296.jpeg)

Highlights w o halation796×685 125 KB](/uploads/short-url/6tr2qi0iL8hmh6a1jV0u0wFy56N.jpeg?dl=1)

Area with highlights and contrasts **with** halation. Looks pleasing and halation performs as expected.

[[![Highlights w halation](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/9/29ae738464e7414d2a8ffc1b1019b6dbfd2e882f_2_345x287.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/9/29ae738464e7414d2a8ffc1b1019b6dbfd2e882f_2_345x287.jpeg)

Highlights w halation798×666 107 KB](/uploads/short-url/5WJkQUcBvQT3W4Lg9rxl4fV2BLp.jpeg?dl=1)

Midtone area **without** halation:

[[![Midtones w o halation](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/7/a794c7fc81688a7d4b5b697d6f750303c7ed2cc9_2_517x381.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/7/a794c7fc81688a7d4b5b697d6f750303c7ed2cc9_2_517x381.jpeg)

Midtones w o halation1398×1033 409 KB](/uploads/short-url/nUuuZgq9Yk8s0SGJFf1FXL05cGR.jpeg?dl=1)

Midtone area **with** halation: Everything seems very glowy, as if shot with a very strong promist filter. Even the darker areas at the bottom of the tree are washed out. This is not usually expected behavior of film stock, even when the halation-protection layer is removed (Cinestill etc.)

[[![midtones w halation](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/f/4f4428bded26d8bee9da89c42f889db64afc67fd_2_517x383.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/f/4f4428bded26d8bee9da89c42f889db64afc67fd_2_517x383.jpeg)

midtones w halation1393×1032 348 KB](/uploads/short-url/bjdKwNdP5fqtzUK8trcy8rBrqep.jpeg?dl=1)

---

## #343 **** (@Thomsen) · 2025-09-26 11:58

> if it’s just a matter of changing these values, i can update the default.

Playing with the halation settings, I cannot pull back this effect in the midtones without reducing the halation of the whole image.

Example of a Cinestill 800T scan. This must be the most halation-prone film out there, but even though the highlights are blooming like crazy, the midtones and shadows retain perfect clarity.

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/b/9b600dae69cfcfa6a419de0bbbec6640e57e9f47_2_690x459.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/b/9b600dae69cfcfa6a419de0bbbec6640e57e9f47_2_690x459.jpeg)

image2048×1365 1.05 MB](/uploads/short-url/mavNGR2fIXN73Chooy85usPm8lh.jpeg?dl=1)

---

## #345 **** (@Thomsen) · 2025-09-26 12:25

Sorry for the tripple-post, new to the forum

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

But in the OP, the halation doesn’t seem to affect the midtones the same way:

> **@arctic** (帖子 #1):
> tree_branches_kodak_gold_200_crystal_archive_preflash005_4Y10M_04pe_2ev_halation31440×1920 5.75 MB

---

## #346 **jo** (@hanatos) · 2025-09-26 12:44

hmm maybe the difference in the interplay between couplers and halation? did you have couplers active (the default is yes)? i’ll experiment a bit and keep an eye on this. don’t want to make midtones all mushy, i agree.

---

## #347 **** (@Thomsen) · 2025-09-26 12:51

Couplers are active yes. But increasing coupler value also make the image brighter for some reason. In the OP they only seem to affect saturation and color depth.

With all this unexpected behavior I am wondering if I’ve set up something wrong, or if it’s because I am running the Windows nightly build?

Do you get the same midtone degredation on Linux?

Is my node tree set up correctly?

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/a/dac86da54ac3eb7979864bacf9c17d0dbb545b94_2_517x181.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/a/dac86da54ac3eb7979864bacf9c17d0dbb545b94_2_517x181.jpeg)

image1234×433 73.2 KB](/uploads/short-url/vdrvgd9aEZe21DjJa7xQYFwKD2c.jpeg?dl=1)

---

## #348 **jo** (@hanatos) · 2025-09-26 12:56

uhm are you opening the filmsim lut as the main image file? should look like this:

[[![20250926_14h55m24s_grim](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/b/ebe38951587ba05103b070693de5270235615cce_2_690x226.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/b/ebe38951587ba05103b070693de5270235615cce_2_690x226.png)

20250926_14h55m24s_grim2082×684 85.5 KB](/uploads/short-url/xELHoWR7v6SpLZ8xQbOhETMn3Vc.png?dl=1)

---

## #349 **** (@Thomsen) · 2025-09-26 12:59

> **@hanatos** (帖子 #348):
> uhm are you opening the filmsim lut as the main image file? should look like this:

Sorry, the filmsim lut was just on top of the input.

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/5/65b2d58a93a382be6a21574d43945443dbe79b71_2_689x229.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/5/65b2d58a93a382be6a21574d43945443dbe79b71_2_689x229.jpeg)

image1231×409 76.9 KB](/uploads/short-url/evFnf8uPhAmx6A3WzsmdAxCEH17.jpeg?dl=1)

Here it is, matching yours, and still the same midtone degredation.

---

## #350 **jo** (@hanatos) · 2025-09-26 13:06

oh absolutely, i think i can reproduce what you mean.

---

## #351 **** (@tankist02) · 2025-09-26 17:54

I see dark brownish greens in ART with AgX when I select Kodak Portra 400. Greens get more greenish if I switch to Kodak Gold 200

---

## #352 **nosle** (@nosle) · 2025-09-26 21:04

So some samples from the image at the top of this thread. Replicating the settings listed in first post.

[[![2025-09-26-225941_1139x707_scrot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/0/405839773b44957b95b9284cb2e4f4def8df42b9_2_690x428.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/0/405839773b44957b95b9284cb2e4f4def8df42b9_2_690x428.png)

2025-09-26-225941_1139x707_scrot1139×707 547 KB](/uploads/short-url/9bdzQvvAB4iT33ouWuzGaOagmFj.png?dl=1)

[[![2025-09-26-230056_1517x967_scrot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/1/0157c01d07b8baad8141f5350c57525425edb07c_2_690x439.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/1/0157c01d07b8baad8141f5350c57525425edb07c_2_690x439.png)

2025-09-26-230056_1517x967_scrot1517×967 1.32 MB](/uploads/short-url/bStSwNHsO1iSYNZBhtW71yG08s.png?dl=1)

I can’t replicate settings in vktd as the recipes are for agx and the settings have different scales etc. but the issue is that the colours are way off and dramatically tinted.

This is the reference from above I’m replicating the third image in his list of samples.

 [[![图片413](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/5/f52a4fe7f32be668584e1c2b24133c22f688ee4d_2_222x333.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/5/f52a4fe7f32be668584e1c2b24133c22f688ee4d_2_222x333.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/5/f52a4fe7f32be668584e1c2b24133c22f688ee4d_2_222x333.png)

The portra endura paper is way more brown/yellow for me than the samples

---

## #353 **jo** (@hanatos) · 2025-09-27 15:28

thanks for the accurate description with examples! i’m not currently at a computer, will look at this when i’m back.

just to rule out simple things, what is your colour management setup?

---

## #354 **nosle** (@nosle) · 2025-09-27 16:09

Display is characterized and run colormngr, xicc to load a system profile (no de, just openbox) calibration device is rather old non pro thing.

Would be interesting to see what others get with some of those images up thread.I feel something happened along the way. Just unsure if it’s my setup/ workflow or changes to the software.

---

## #355 **jo** (@hanatos) · 2025-09-27 16:17

ah, did you tell vkdt to pick up the profile via vkdt read-icc?

---

## #357 **** (@Thomsen) · 2025-09-27 17:10

> **@hanatos** (帖子 #350):
> oh absolutely, i think i can reproduce what you mean.

The halation also seems to soften the grain, and the couplers have odd behavior when halation is turned off. Perhaps something with the order of operations, or at least something about the way these settings are affecting each other.

> **@nosle** (帖子 #352):
> This is the reference from above I’m replicating the third image in his list of samples.

The portra endura paper is way more brown/yellow for me than the samples

I did manage to get some nicer greens here by cooling the white balance and increasing saturation before the film conversion - effectively increasing the color separation.

“Apply preset whitebalance-camera” was a good starting point, but I had to make it even cooler to match the greens of the reference from the first post.

One thing though: The “tune m” and “tune y” controls could benefit from some more range. Plus minus 1 seems a bit limiting.

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/a/1ae4aaf09ba92e04cb674d111a69ce2962ccbb29_2_690x564.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/a/1ae4aaf09ba92e04cb674d111a69ce2962ccbb29_2_690x564.jpeg)

image1335×1093 303 KB](/uploads/short-url/3PUkCtZSJZJMCTma4xCtRjlIL4B.jpeg?dl=1)

---

## #358 **nosle** (@nosle) · 2025-09-27 17:42

Nope! Checking that flag now but can’t find documentation. Spits out tags without launching vkdt. The difference between profiled and not is quite minor with my setup though.

> **@Thomsen** (帖子 #357):
> I did manage to get some nicer greens here by cooling the white balance and increasing saturation before the film conversion - effectively increasing the color separation.
“Apply preset whitebalance-camera” was a good starting point, but I had to make it even cooler to match the greens of the reference from the first post.

Your results look close. Quite the process though I don’t remember that being required.

> **@Thomsen** (帖子 #357):
> “Apply preset whitebalance-camera” was a good starting point,

yep, I did this as well

---

## #359 **** (@Thomsen) · 2025-09-28 07:53

> **@nosle** (帖子 #358):
> Your results look close. Quite the process though I don’t remember that being required.

From what I see it looks like the image is going through the same color conversion process as in the OP.

If we had to use color curves or local adjustments to match the OP, something would probably be off with the conversion. But I’ve only done edits that affect the whole image, pulling it colder and increasing saturation - and the result maches pretty closely.

From my experience, finding the perfect white balance is a very important first step before applying any color conversion.

---

## #360 **** (@Thomsen) · 2025-09-28 08:47

This one was actually a bit more difficult to match, especially the skin tones.

When increasing the saturation in the color node before the conversion, I noticed color artifacts. Especially the greens turned darker and noisy.

[@hanatos](/u/hanatos) Is the filmsim node working in a limited colour space?

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/d/cd5c6a9046d1131acc0e30c5a6b98ff8b99f1161_2_690x437.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/d/cd5c6a9046d1131acc0e30c5a6b98ff8b99f1161_2_690x437.jpeg)

image1252×793 272 KB](/uploads/short-url/tiHSHQxKderyxQvqLEbRJvpNtct.jpeg?dl=1)

---

## #361 **** (@mikae1) · 2025-09-28 20:07

Just want to say that I’m following this thread with great interest again.

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 It’s another reminder that I need to learn vkdt. A video introduction explaining the basic concept would be a dream come true. I haven’t been able to find one.

> **@Thomsen** (帖子 #357):
> The halation also seems to soften the grain

Yeah, I noticed that too. Seems it goes in the wrong order?

---

## #362 **Upperechelonstr8up** (@upperechelonstr8up) · 2025-09-29 06:08

Please continue this project and expand its possibilities! This is the greatest film emulator that I’ve ever seen and has been **LONG** overdue, i will be keeping up to date on any future developments to this project!

---

## #363 **Benjamin** (@piratenpanda) · 2025-09-29 06:22

Yeah same goes for me. How can we support you [@arctic](/u/arctic)? Do you accept donations?

---

## #364 **jo** (@hanatos) · 2025-09-29 06:26

> **@Thomsen** (帖子 #357):
> One thing though: The “tune m” and “tune y” controls could benefit from some more range. Plus minus 1 seems a bit limiting.

these are finetuning parameters. i’m hiding the actual wb coefficients from the gui to reduce clutter, which may not be a good choice. in general this paper exposing light white balancing is difficult to get right, i’ve had issues with the range quite a bit. as a workaround, you can always click the number and dial something way off scale into it (cumbersome, but at least it works).

> **@nosle** (帖子 #358):
> Nope! Checking that flag now but can’t find documentation. Spits out tags without launching vkdt. The difference between profiled and not is quite minor with my setup though.

okay, note to self: i’ll have to improve these docs. `vkdt read-icc your-monitor-profile.icc` will create a file `display.profile` containing gamma + rec2020-to-display matrix that will be read by vkdt if it’s in `~/.config/vkdt/display.DP-1` say, if your monitor is caled `DP-1` by wayland or xorg. more modern wayland configurations allow us to use rec2020 as compositor colour space (for instance kde and hyprland do), so you can put the identity matrix into this file. i’ll update the docs…

> **@Thomsen** (帖子 #360):
> When increasing the saturation in the color node before the conversion, I noticed color artifacts. Especially the greens turned darker and noisy.

these might be out of spectral locus, judging by the noisy transition.

> **@Thomsen** (帖子 #360):
> @hanatos Is the filmsim node working in a limited colour space?

it works in spectral. which also means that it’ll upsample any input colour to a spectrum before working with it. can you try to apply the `gamut` preset? i.e. press `ctrl-p` and type `gamut` and then `enter` in darkroom mode? it will load a hue preserving table into the `colour` module that will allow you to push saturation without exceeding the spectral locus limit. the spectral upsampling is tolerant for non-physical input, but the results will only mean so much if you’re way overboard.

---

## #365 **jo** (@hanatos) · 2025-09-29 07:27

> **@piratenpanda** (帖子 #363):
> Yeah same goes for me. How can we support you @arctic? Do you accept donations?

agree here. anything we can do to help? i’d assume there would be some useul work to be done on the project/code, i think maaybe we could

- help gain insights on order of operations
- look at interactions between grain, halation, and couplers

and other interesting directions would be

- add more film stock, some mentioned in this thread
- add b/w film processing code path

i suppose since b/w is mostly reading some literature and then stripping off all colour features maybe one of us enthusiasts could do a first step. adding more stock i think requires some of the careful eyeballing, data massaging, normalisation, and then ingestion into the code that [@arctic](/u/arctic) has done. this would at least require some detailed guide how to do it.

---

## #366 **** (@Thomsen) · 2025-09-29 12:57

> **@hanatos** (帖子 #364):
> these are finetuning parameters. i’m hiding the actual wb coefficients from the gui to reduce clutter, which may not be a good choice. in general this paper exposing light white balancing is difficult to get right, i’ve had issues with the range quite a bit. as a workaround, you can always click the number and dial something way off scale into it (cumbersome, but at least it works).

Ahh I see. I am experiencing the same white balance difficulties, so maybe including the wb coefficients would be benefitial? Perhaps a collapsible sub-menu called WB adjustments or something?

> **@hanatos** (帖子 #364):
> it works in spectral. which also means that it’ll upsample any input colour to a spectrum before working with it. can you try to apply the gamut preset? i.e. press ctrl-p and type gamut and then enter in darkroom mode? it will load a hue preserving table into the colour module that will allow you to push saturation without exceeding the spectral locus limit. the spectral upsampling is tolerant for non-physical input, but the results will only mean so much if you’re way overboard.

Nothing really happens when I load up the preset.

Is there some way of increasing the saturation in a node after the filmsim one?

I’ve been searching for a simple HSL tool or something, but cannot find any means of increasing the saturation besides the Color node, which seemingly can’t be added a second time after the filmsim.

> **@mikae1** (帖子 #361):
> Thomsen:

The halation also seems to soften the grain

Yeah, I noticed that too. Seems it goes in the wrong order?

</blockquote>
</aside>

I agree that there might be something wrong with the order of operations, as it affect the grain.

Also, I notice that the halation stays unaffected when changing the film exposure. Halation in film-negatives is very exposure dependent - only the brightest of exposures manages to burn all the way in and get reflected as halation.

[@arctic](/u/arctic) 's original implementation seems to only affect high contrast and high exposure areas, not the totality of the image.

I might try to do a halation comparison between the python script and the VKDT when I have the time.

---

## #367 **Anna** (@betazoid) · 2025-10-01 15:03

For someone who wants to try this for the first time: what is the recommended „version“ - the original pythom program, ART or vkdt?

---

## #368 **nosle** (@nosle) · 2025-10-01 15:43

The original is in a different league imho. I’t does grain and halation in a way that to my eye is way closer to film. Those things are also important to the film look.

Unfortunately it’s also in a different league in terms of being incredibly slow and cumbersome to use!

---

## #369 **Anna** (@betazoid) · 2025-10-02 10:48

Ok the only way I could make this work, more or less, was via vkdt. I tried very hard with ART but it kept complaining about wrong input values or so.

In vkdt nightly appimage read-icc does not seem to work any more, or it works differently now. It shows the icc profile values but then the next time I am starting vkdt, it picks srgb as the display profile. Why did you break this [@hanatos](/u/hanatos)? Well and I could not make the appimage run on/with (x)wayland, only on kde-plasma-x11. However, I don’t know which gpu vkdt uses, Nvidia or Intel. I feels like it’s using Intel.

Edit: I made the original work meanwhile. Turns out, I had to detach the mail tools window from the program window in order to see the run button.

These are lots of tools to play around with for a long time…

---

## #370 **Anna** (@betazoid) · 2025-10-02 11:47

What about color management in the original python tool? My laptop has more or less a P3 screen - if I choose DisplayP3 as output color space, will I see in about accurate colors? Sorry, I didn’d read the whole thread, maybe someone already asked this?

---

## #371 **Anna** (@betazoid) · 2025-10-02 13:28

Very cool tool. Hope it will become a darktable module eventually.

---

## #372 **jo** (@hanatos) · 2025-10-02 15:18

> **@Thomsen** (帖子 #366):
> I agree that there might be something wrong with the order of operations, as it affect the grain.

grain is added after halation, and also the halation is applied to linear raw input and the formulas are equivalent to the python. i mean it seems to make sense to try and put some extra protection for low/mid luminance areas, but the python also doesn’t have it.

the one thing i can see is slightly different is couplers vs halation.

---

## #373 **jo** (@hanatos) · 2025-10-02 15:51

> **@betazoid** (帖子 #369):
> Ok the only way I could make this work, more or less, was via vkdt. I tried very hard with ART but it kept complaining about wrong input values or so.

> **@betazoid** (帖子 #369):
> Why did you break this @hanatos?

haha, breathe! i doubt any of the three projects can distill any actionable way of debugging from your text here.

> **@betazoid** (帖子 #370):
> What about color management in the original python tool? […]
if I choose DisplayP3 as output color space, will I see in about accurate colors?

no.

> **@betazoid** (帖子 #371):
> Very cool tool.

yes

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

---

## #374 **Sébastien Guyader** (@sguyader) · 2025-10-02 16:47

> **@betazoid** (帖子 #369):
> I tried very hard with ART but it kept complaining about wrong input values or so.

Several issues can cause this message, 2 of them are the presence of old data in the cache (so, clean your ART cache first) and the ART script not finding your AGX python environment.

---

## #375 **** (@tankist02) · 2025-10-02 20:12

If you could provide more details about your ART + AgX setup may we could help?

---

## #376 **Anna** (@betazoid) · 2025-10-02 23:29

Never mind, I got it working. I had to find the right path for the venv.

---

## #377 **Anna** (@betazoid) · 2025-10-02 23:32

> **@hanatos** (帖子 #373):
> no.

But I think colors are in about correct if output profil and monitor color space are appriximately the same. The trouble is only that when I save a pic from agx-emulsion, no profile is embedded in the file. Maybe I can fix that.

---

## #378 **Anna** (@betazoid) · 2025-10-02 23:36

> **@hanatos** (帖子 #373):
> haha, breathe! i doubt any of the three projects can distill any actionable way of debugging from your text here.

```
anna@zbook:~/Downloads$ ./vkdt-rawler-glfw3.4-0.9.99-815-gdc9dbc4c-x86_64.AppImage
[gui] vkdt 0.9.99-815-gdc9dbc4c (c) 2020--2025 johannes hanika
[gui] glfwGetVersionString() : 3.4.0 Wayland X11 GLX Null EGL OSMesa monotonic
[gui] monitor [0] eDP-1 at 0 0
[gui] vk extension required by GLFW:
[gui] VK_KHR_surface
[gui] VK_KHR_wayland_surface
[ERR] failed to init gui/swapchain

```

This is on Debian 13/new HP laptop with Nvidia+Intel/KDE Plasam/Wayland

```
anna@zbook:~/Downloads$ ./vkdt-rawler-glfw3.4-0.9.99-815-gdc9dbc4c-x86_64.AppImage read-icc /home/anna/hp.icc
tag rXYZ 0.507935 0.240265 0.0039978
tag gXYZ 0.29306 0.691589 0.0451508
tag bXYZ 0.163208 0.0681458 0.775757
tag rTRC 2.20703
tag gTRC 2.20703
tag bTRC 2.20703
anna@zbook:~/Downloads$ ./vkdt-rawler-glfw3.4-0.9.99-815-gdc9dbc4c-x86_64.AppImage
[gui] vkdt 0.9.99-815-gdc9dbc4c (c) 2020--2025 johannes hanika
[gui] glfwGetVersionString() : 3.4.0 Wayland X11 GLX Null EGL OSMesa monotonic
[gui] monitor [0] eDP-1 at 0 0
[gui] vk extension required by GLFW:
[gui] VK_KHR_surface
[gui] VK_KHR_xcb_surface
[gui] no gamepad found
[gui] no display profile file display.eDP-1, using sRGB!

```

looks like new read-icc is not finished yet?

Edit I got vkdt running on plasma/wayland with these environment variables:

`env SDL_VIDEODRIVER=x11 XDG_SESSION_TYPE=x11 ./vkdt-rawler-glfw3.4-0.9.99-815-gdc9dbc4c-x86_64.AppImage`

Edit: I got everything working now, agx-emulsion, ART and vkdt. Color management in vkdt works too although its a bit clumsy. However, I am getting different results with the three apps. ART and agx-emulsion are more similar, vkdt seems to have a yellow cast or so, of course it is possible to fix that with the white balance but the source files are not so different and have very similar white balances. I will post examples later.

---

## #379 **jo** (@hanatos) · 2025-10-05 08:18

> **@betazoid** (帖子 #378):
> looks like new read-icc is not finished yet?

ah. i had to rewrite it in a proper language because the arch linux packaging system was rightfully complaining that the python version introduced a numpy dependency. seemed a bit heavy for a matrix multiplication.

---

## #380 **Matej Špoljar** (@Matej_Spoljar) · 2025-10-07 21:21

this is all super interesting, it really is probably the best film emulation tool, besides the ones that you can find in Baselight or maybe Genesis

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 but i’m also getting weird brown and yellow greens, especially with portra, the example images are all very different from the samples (uv agx version and vkdt)

---

## #381 **** (@tankist02) · 2025-10-07 23:57

I also get weird colors (too much reds) with AgX in ART. Using Kodak Gold 200 alleviates the problem a bit, but not enough. What helps is increasing Dir couplers amount and reducing Film gamma factor.

---

## #382 **** (@mino) · 2025-10-08 05:09

I experienced this also. Switching the simulated paper to Fuji Crystal gave me much nicer colours.

---

## #383 **Anna** (@betazoid) · 2025-10-08 08:04

Can also coform brown greens.

---

## #384 **** (@Thomsen) · 2025-10-08 09:58

I love how the simulation gives a cinematic vibe to this busy pizza shop.

Fujifilm X-m5 with a 35mm f0.95 lens.

Kodak Ektar 100 film with Kodak Supra Endura Paper

[[![Stockholm (18)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/b/fb47c493256bdd819a3d387618a0e724e7e53b1f_2_690x345.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/b/fb47c493256bdd819a3d387618a0e724e7e53b1f_2_690x345.jpeg)

Stockholm (18)6240×3120 4.77 MB](/uploads/short-url/zQVBDrApuK9zql4PlToRPpdf56v.jpeg?dl=1)

[[![Stockholm (17)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/d/0d5619d74bb01e566c3b2bcb3500fd3127b2e2f2_2_690x345.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/d/0d5619d74bb01e566c3b2bcb3500fd3127b2e2f2_2_690x345.jpeg)

Stockholm (17)6240×3120 4.75 MB](/uploads/short-url/1TYG0qQN5aie35MbhCQ8QlT1a02.jpeg?dl=1)

---

## #385 **jo** (@hanatos) · 2025-10-08 10:04

i have some local changes that i might test a bit more and then push. first is about explicit mid-tone protection for halation.

new version:

[[![2025-10-08-113304_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/4/24035cf8c84a6183901dd6c27df6189b407a1931_2_690x540.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/4/24035cf8c84a6183901dd6c27df6189b407a1931_2_690x540.png)

2025-10-08-113304_hyprshot2071×1621 2.61 MB](/uploads/short-url/58AosrH1EpHq4XnVfxYSH3We8Hn.png?dl=1)

old version, note how the cable on the tree is quite a bit less defined (might need to a/b the images):

[[![2025-10-08-113254_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/7/7767ca1a7b29501a68ae3115925352a68595e2c5_2_690x540.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/7/7767ca1a7b29501a68ae3115925352a68595e2c5_2_690x540.png)

2025-10-08-113254_hyprshot2071×1621 2.49 MB](/uploads/short-url/h2jbAp7CAnkVkWa1AfY1QigR40t.png?dl=1)

without halation, for reference:

[[![2025-10-08-113249_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/4/f401321ab995fde7b30b7085e33bb10919902a58_2_690x540.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/4/f401321ab995fde7b30b7085e33bb10919902a58_2_690x540.png)

2025-10-08-113249_hyprshot2071×1621 2.66 MB](/uploads/short-url/yOz40m0xYCqsPSFHSMrvYIcxPjW.png?dl=1)

and the second is about grain. current default, single octave blue noise:

[[![2025-10-08-112957_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/1/11d16494ef226c9babafaeb647f175eba328ae79_2_690x540.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/1/11d16494ef226c9babafaeb647f175eba328ae79_2_690x540.png)

2025-10-08-112957_hyprshot2071×1621 2.45 MB](/uploads/short-url/2xCJPwPhnRzz9Dbxzejs5MIQW93.png?dl=1)

new version, two octaves of blue noise, has a bit more random looking breakup of repetative strutures:

[[![2025-10-08-112946_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/d/dd201d4ae112f8fd0a3a276c463fb8fc923f2324_2_690x540.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/d/dd201d4ae112f8fd0a3a276c463fb8fc923f2324_2_690x540.png)

2025-10-08-112946_hyprshot2071×1621 2.48 MB](/uploads/short-url/vyakcorhSbl06I2CzO53aqShwFu.png?dl=1)

---

## #386 **** (@Thomsen) · 2025-10-08 10:14

Looks very promising! Grain is definitely more pleasing.

Halation also looks more usable without the midtone degredation.

The glow seems a bit sharp on the edges though - perhaps it needs a bit more falloff?

---

## #387 **** (@Thomsen) · 2025-10-08 12:54

Some halation samples from Cinestill Film that I’ve shot, if it can be of any use:

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/f/0f482e0f3e6d60436ca2844a0032caf9c5aae0a1_2_690x422.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/f/0f482e0f3e6d60436ca2844a0032caf9c5aae0a1_2_690x422.jpeg)

image1114×682 177 KB](/uploads/short-url/2bbO1qm16UWYGXkdkNNnPpQ3LDH.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/3/4367f4a00ba5993a36f18e8cca977b811f252e4c_2_690x300.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/3/4367f4a00ba5993a36f18e8cca977b811f252e4c_2_690x300.jpeg)

image1239×540 162 KB](/uploads/short-url/9CiIhKAXeO5IvkgUZf5wrz7j1kU.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/7/5731e769bfb732d68a683a285b1649d09a2a4752_2_689x476.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/7/5731e769bfb732d68a683a285b1649d09a2a4752_2_689x476.jpeg)

image1279×883 353 KB](/uploads/short-url/crmsr6C29fiyIoYlYWFPwpIkGps.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/e/4e3a1419ceea8d803672e14bfbf8012473788704_2_689x425.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/e/4e3a1419ceea8d803672e14bfbf8012473788704_2_689x425.jpeg)

image1371×846 475 KB](/uploads/short-url/ba1FS2gipmXd0RcIupiMDwbvbus.jpeg?dl=1)

---

## #388 **jo** (@hanatos) · 2025-10-08 13:02

thanks! somehow still looks a bit softer than my falloff:

[[![2025-10-08-145939_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/d/1d9d40812fc335fa44dd6260936466dcbfa5820f_2_690x546.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/d/1d9d40812fc335fa44dd6260936466dcbfa5820f_2_690x546.png)

2025-10-08-145939_hyprshot1975×1563 1.31 MB](/uploads/short-url/4dYKXAA0w92nRcoU4t2iWTwrfNJ.png?dl=1)

[[![2025-10-08-145932_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/a/ca480916e1fba372e24c373b031e87f079998341_2_690x546.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/a/ca480916e1fba372e24c373b031e87f079998341_2_690x546.png)

2025-10-08-145932_hyprshot1975×1563 1.32 MB](/uploads/short-url/sRsMDbVonIk9ZY5rdX3npm2zhcd.png?dl=1)

[[![2025-10-08-145814_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/9/e98110548f0ca9e8ebc20d0449b72b8a131b1763_2_690x546.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/9/e98110548f0ca9e8ebc20d0449b72b8a131b1763_2_690x546.png)

2025-10-08-145814_hyprshot1975×1563 1.16 MB](/uploads/short-url/xjFLE9rKAzbsXOJS0hRebgv7vH5.png?dl=1)

[[![2025-10-08-145810_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/b/0b43962aa4dbd1d7a67a67d77d2e7d371240317f_2_690x546.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/b/0b43962aa4dbd1d7a67a67d77d2e7d371240317f_2_690x546.png)

2025-10-08-145810_hyprshot1975×1563 1.15 MB](/uploads/short-url/1BE3so6yJrCoQO2rPdvSy5pMTnx.png?dl=1)

[[![2025-10-08-145739_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/3/939e9ad31d60be84202e7b4e7a86c7be15b3d0c0_2_690x546.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/3/939e9ad31d60be84202e7b4e7a86c7be15b3d0c0_2_690x546.png)

2025-10-08-145739_hyprshot1975×1563 1.1 MB](/uploads/short-url/l3TZPLCUAs85dFkZJaDd5UI7EVa.png?dl=1)

[[![2025-10-08-145734_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/1/a1b3cbc2cc8a5927b4d53e5924300bab65364953_2_690x546.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/1/a1b3cbc2cc8a5927b4d53e5924300bab65364953_2_690x546.png)

2025-10-08-145734_hyprshot1975×1563 1.09 MB](/uploads/short-url/n4u5c0Ecm98np6zd0l9j0LGOfTl.png?dl=1)

---

## #389 **** (@Toast) · 2025-10-08 16:41

It looks like the git repo has not been updated for some time. Is the original project still being worked on, or is the discussion now around other projects incorporating / extending it?

---

## #390 **** (@commutergraphics) · 2025-10-08 20:05

I wonder if an rgb primaries style colour adjuster in this would help?, to just fix weird colours without having to know which simulation parameter to tweak

---

## #391 **** (@tankist02) · 2025-10-08 20:11

Maybe, but I prefer to tweak everything in one place if possible - AgX parameters.

---

## #392 **** (@commutergraphics) · 2025-10-08 20:14

in agx in darktable (the not film simulator), a primaries section was added to allow for quick tweaks, same as in sigmoid

---

## #393 **** (@tankist02) · 2025-10-08 20:17

I know, I follow DT development, though I stopped using it. Too complicated for my taste, I prefer how ART allows for quick edits with great results.

---

## #394 **Todd Prior** (@priort) · 2025-10-08 20:22

I haven’t used it but there might be a primaries ctl in ART… in case someone needs it… so many features have been added to ART with these scripts…

---

## #395 **** (@tankist02) · 2025-10-08 20:26

ART has global Primaries correction in Channel Mixer tool (Colors tab). And local adjustments via CTL script Rel. Color Filter… in Color/Tone Correction.

---

## #396 **** (@commutergraphics) · 2025-10-08 20:28

yes, does seem to get new features from other editors pretty quickly

---

## #397 **Todd Prior** (@priort) · 2025-10-08 20:32

Ya I wasn’t at my computer…I think this is the one I was remembering…

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/6/9/69c0f69c287f2695bdac8bfadd7fd1e45b6b13fb.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/6/9/69c0f69c287f2695bdac8bfadd7fd1e45b6b13fb.png)

image302×436 10.7 KB](/uploads/short-url/f5xyuOH6jG2DogafUWsZbdOK2f1.png?dl=1)

---

## #398 **** (@tankist02) · 2025-10-08 20:37

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/e/cefecd85fea272e8d6991ed83140b12041f829ad.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/e/cefecd85fea272e8d6991ed83140b12041f829ad.png)

image478×849 34.5 KB](/uploads/short-url/txagPrVYRqBSbMEkOaX4llVAh1r.png?dl=1)

I tried this one for a quick edit and indeed it allows to tame reds in AgX when using some Kodak film/paper combinations.

---

## #399 **** (@Bruno) · 2025-10-13 17:33

Hey [@arctic](/u/arctic), I am in the process of looking for a topic I can write my bachelor thesis about and I was really interested in writing about properly simulating the exposure of analog film digitally. Looking through the internet I could never find someone who had already done this, Only by accident I stumbled upon your project and was blown away by this process you have developed here and by the results as well. This really is something else.

After playing around with this a bit i am wondering: how can I save/export images?

---

## #400 **Ted Cousins** (@cedric) · 2025-10-13 19:15

> **@Bruno** (帖子 #399):
> I am in the process of looking for a topic I can write my bachelor thesis about and I was really interested in writing about properly simulating the exposure of analog film digitally. Looking through the internet I could never find someone who had already done this, Only by accident I stumbled upon your project and was blown away by this process you have developed here and by the results as well. This really is something else.
After playing around with this a bit i am wondering: how can I save/export images?

RawTherapee comes with Film Simulation built-in which is just what you’re looking for.

It uses a type of PNG image called a HaldCLUT and you can download more from the internet and add them to RT.

Some here: [Pat David: Film Emulation in RawTherapee](https://patdavid.net/2015/03/film-emulation-in-rawtherapee/)

Store them here:

C:\Users<username>\AppData\Local\RawTherapee5\HaldCLUT

hope this helps …

---

## #401 **** (@mikae1) · 2025-10-13 19:30

> **@Bruno** (帖子 #399):
> After playing around with this a bit i am wondering: how can I save/export images?

File

[![:arrow_right:](https://discuss.pixls.us/images/emoji/apple/arrow_right.png?v=12)](https://discuss.pixls.us/images/emoji/apple/arrow_right.png?v=12)

 Save Selected Layers…

You can also use [vkdt](https://github.com/hanatos/vkdt) to access another implementation of [@arctic](/u/arctic)’s work.

> **@Bruno** (帖子 #399):
> was blown away by this process you have developed here and by the results as well. This really is something else

I agree. It’s unique.

---

## #402 **おばけちゃん** (@ghost) · 2025-10-14 00:04

First, heartfelt thanks to everyone involved in this project.

Next, and this is not meant as criticism, but your research is seriously insufficient.

The technique itself is not unique — it has been tackled many times before. At its core, this method isn’t limited to film; it’s essentially a re-shoot (virtual camera) simulation.

What makes this project “unique” and valuable is that a surprisingly large portion of what’s going on has been made public. Of course not everything is disclosed.

Here are 2 examples of spectrum-based film-simulation work where at least some hints are publicly available:

1. “Film Simulation for Video Games (SIGGRAPH 2010)” by tri-Ace Inc.

This was developed for a Japanese game project and performed film simulation based on film spec sheets.

[https://research.tri-ace.com/](https://research.tri-ace.com/)

- “Film Simulation for Video Games” SIGGRAPH 2010
- “Physically Based Lighting for Rendering” CEDEC 2010
- “Renderist no tame no camera (kougaku) riron to post effect (Camera, optics theory and post effects for renderists)” CEDEC 2007

<ol start="2">
<li>“C-105 Vison (FilmLight)” by Daniele Siragusano</li>
</ol>

This was developed for TCAMv2 & TCAMv3.

Also related is “Smooth Spectra (SIGGRAPH 2022)”:

- [https://www.youtube.com/watch?v=JtSJr-je8qY&t=8220s](https://www.youtube.com/watch?v=JtSJr-je8qY&t=8220s)
- [https://blog.selfshadow.com/publications/s2022-spectral-course/s2022_spectral_course_notes.pdf](https://blog.selfshadow.com/publications/s2022-spectral-course/s2022_spectral_course_notes.pdf)

In every example, these methods do not perfectly reproduce what you would capture with a film camera. They can be applied toward that goal, but many pieces of information are missing to reach a finished, high-fidelity simulation.

In the current implementation, layers saved via the GUI are exported as 8-bit output.

As suggested, you can either use vkdt, modify the experimental GUI to write non-8-bit output when saving layers, or process the image directly by calling the functions defined in the Python program.

---

## #403 **Mica** (@paperdigits) · 2025-10-14 01:54

Hi [@ghost](/u/ghost) and welcome to the forum.

> **@ghost** (帖子 #402):
> Next, and this is not meant as criticism, but your research is seriously insufficient.

So what is lacking in the research and implementation? Can you elaborate?

---

## #404 **おばけちゃん** (@ghost) · 2025-10-14 02:44

Sorry, I forgot to include the video link for C-105 Vision.

This is it: [Colour Online: Creating the look for Netflix’s ‘Tribes of Europa’](https://vimeo.com/521822858#chapter=2896841)

---

## #405 **おばけちゃん** (@ghost) · 2025-10-14 02:59

Thanks - My point was specifically about Bruno’s claim that “I could never find someone who had already done this” despite planning a thesis. If my comment violated the forum’s policy or was otherwise inappropriate, I apologize.

---

## #406 **Mica** (@paperdigits) · 2025-10-14 03:01

> **@ghost** (帖子 #405):
> If my comment violated the forum’s policy or was otherwise inappropriate, I apologize.

Nope, looks like interesting reading, thanks for clarifying!

---

## #407 **István Kovács** (@kofa) · 2025-10-14 06:49

That’s not why primaries were added. The primaries are **the** core feature; the curve is of lesser importance. But let’s not drag dt agx into unrelated discussions.

---

## #408 **** (@Bruno) · 2025-10-15 08:42

Hi [@ghost](/u/ghost) ,

My wording was a bit misleading, what I meant that I couldnt find a publicly available and working tool which tries to emulate the process of exposing negative color film layers and then printing/scanning it. A coplete pipeline from a raw image to a finished simulation. Of course there has been research done in this field and similar tools have been developed, be it for slightly different purposes.

---

## #409 **** (@Bruno) · 2025-10-15 08:44

Thanks!

---

## #410 **Andrea** (@arctic) · 2025-10-15 20:44

hi everyone, I am very sorry for the long absence. life had a little toll on me, but i am slowly catching up and planning to get back up to speed

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 and update myself on what i missed.

i agree [@ghost](/u/ghost) that the work here is not to be considered fully novel. i mean, the core knowledge is so digested that there are full books about it, including the ones i based most of the things, e.g. Digital Color Management by Giorgianni Madden 2008 Wiley.

and there are probably countless efforts in this direction.

i believe the novel aspects are:

- the use of a cutting edge spectral upsampler by [@hanatos](/u/hanatos)
- the use of datasheet-only spectroscopic data as input, and the way profiles are slightly tuned to ensure a stable gray output with exposure
- the simple coupler inhibition model to achieve a decent saturation
- the multilayer grain model

and in general the project started as a grain simulation that found its best way to be implemented into the full photography process model. so i agree that there is a lot of common sense photography knowledge reimplemented in this project (because wheels like to be built many times

[![:stuck_out_tongue:](https://discuss.pixls.us/images/emoji/apple/stuck_out_tongue.png?v=12)](https://discuss.pixls.us/images/emoji/apple/stuck_out_tongue.png?v=12)

, it’s them not us)

[@Bruno](/u/bruno) if you wanna chat or have some input/help let me know, it’s fun that you are thinking of doing a thesis on these topics. i am even a little jealous

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

---

## #411 **jo** (@hanatos) · 2025-10-16 06:38

nice to see you’re back. sorry to hear you had a hard time, hope for the best going forward.

i believe [@ghost](/u/ghost) was referring to [@Bruno](/u/bruno)’s comment about research about prior work, assuming this was about references to literature. and also research is about diligently assembling tiny pieces until they become something new. i wouldn’t diminish your work here. none of us was capable of ingesting new film stock while you were away, can’t be *that* trivial.

---

## #412 **** (@Toast) · 2025-10-22 09:32

I just read though [Digitizing film using DSLR and RGB LED lights - #22 by damirk](https://discuss.pixls.us/t/digitizing-film-using-dslr-and-rgb-led-lights/18825/22) and wandered if at approach would meld well with this software. I then though, would there be any value in having a light source with a range of different spectrum LEDs that we could cycle through to build a source image with more than just RGB input spectrum?

LEDs are small and it would be easy to have a dense array of different bulbs. They could be software controlled. I’m thinking of a process like this:

1. Take an image with each colour LED and no negative. Use that to figure out the raw response of the sensor+Bayer mask and fix any inconsistencies in backlight brightness uniformity. Also calibrate light brightness and or exposure as required.
2. With film in place take an image with each colour light, correct the captured data with the information from 1.
3. Generate a spectral image and import into the negative processing pipeline.

This would all have to be automated or it would be too cumbersome, so in use, it would be a matter of pressing the setup button with no negative, then pressing the capture button for each negative.

Would that result in a meaningfully better result?

---

## #413 **jo** (@hanatos) · 2025-10-22 09:59

> **@Toast** (帖子 #412):
> Would that result in a meaningfully better result?

probably yes! nothing looks as good as real data… before you start building stuff in hardware, i’d probably validate some of the overall idea via existing data. maybe search here: [Hyperspectral Imaging Open Ecosystem](https://hsi.yale.edu/resource/103) which holds links to hyperspectral images like [Spectral scene database · ISET/isetcam Wiki · GitHub](https://github.com/ISET/isetcam/wiki/Spectral-scene-database) which might be great input for the film simulation. best to combine with a standard format for spectral images, like [https://cgg.mff.cuni.cz/wp-content/uploads/2021/06/jcgt_2021_spectral_exr.pdf](https://cgg.mff.cuni.cz/wp-content/uploads/2021/06/jcgt_2021_spectral_exr.pdf) or [Compression of Spectral Images using Spectral JPEG XL](https://momentsingraphics.de/JCGT2025.html)

---

## #414 **** (@Toast) · 2025-10-22 18:55

Wow, thanks, those are amazing. They are also highlighting that whilst I’m comfortable with hardware, my maths and software may be a bit lacking! I do think the idea is at least physically practical though.

---

## #415 **Anna** (@betazoid) · 2025-10-25 12:33

in the ART and vkdt implementations, is there a recommended workflow? I mean obviously there are inside agxemulsion and outside of the tool slider that do similar things, e.g. change brightness - is it recommended to use the art/vkdt tools first or just do a very broad edit outside agxemulsion and then the rest inside agxemulsion?

Oftentimes I have the following situation: I switch off curves/tonemapping, then I adjust brightness, and then I switch on agxemulsion, and the the photo suddenly get very bright or dark - in such cases, is it recommended to fix this with the agxemulsion sliders or with the ART/vkdt-sliders?

---

## #416 **jo** (@hanatos) · 2025-10-27 08:43

any reason why you’d edit the image first before switching on the film sim? i see it as a display transform and i wouldn’t try to edit an image without film curve first (except when mastering for hdr monitors).

using the film/paper exposures has very different results, use for artistic intent. film exposure is equivalent to exposing the input in a preceeding module.

---

## #417 **Daniel Rheaume** (@RTLdan) · 2025-10-29 23:38

Wow, what an amazing project!

I found out about this Project from Nico at Demystify color. I’m sure you will be seeing a lot more people come in from there!

Anyway, was hoping for a bit of advice!

When I create and use a combination of negative and print LUTs in Davinci Resolve, I’m basically setting up a node structure like this:

IDT (to DWG/DI) → NEGATIVE → PRINTER LIGHTS IF DESIRED → PRINT FILM → ODT (R709/G2.4).

I’m noticing right off the bat I’m getting pretty extreme contrast ratios which are making me need to do a contrast trim somewhere in this chain.

If I put a contrast node before the negative, I’m concerned that I’ll be sending it a log image that it is not properly expecting. I’m usually needing to reduce contrast by about 50% at that stage. Alternatively, I’ve tried putting a contrast node inside a “timing” section between the negative and print nodes. This works, but it seems to sometimes cause strong hue shifts. I couldn’t tell if that’s normal for that timing process, or if I’m messing with the print lut’s expected input and shifting further away from the emulation’s intended math. Finally, I’ve done contrast trims after the print emulation. This definitely looks the most natural since we are essentially grading the printed image, but it leaves parts of our image clipped/crunched because they have already been affected by the curve’s toe/shoulder, so it’s not an ideal way to preserve contrast as a whole, rather it seems best for post look trims.

Am I missing something? Is it a combo of all of the above?

Not sure if there is some intention that I’m missing here as to what each LUT is being fed.

All of your help is much appreciated!

Best,

-Daniel

---

## #418 **Mica** (@paperdigits) · 2025-10-30 03:04

> **@RTLdan** (帖子 #417):
> Wow, what an amazing project!
I found out about this Project from Nico at Demystify color. I’m sure you will be seeing a lot more people come in from there!

Hey [@RTLdan](/u/rtldan) and welcome! There are a few pieces of software discussed here, would you mind telling us which one you are referring to and perhaps link us to the tutorial that references the software in question?

Thanks!

---

## #419 **Daniel Rheaume** (@RTLdan) · 2025-10-30 04:04

Oh, my bad! Sorry for not being more clear - I’m currently experimenting with Spectral Film Lut from Jan Lohse ([GitHub - JanLohse/spectral_film_lut: Generate LUT for film emulation based on film datasheets.](https://github.com/JanLohse/spectral_film_lut)).

I don’t have any tutorial for it other than the readme on that Github!

Also, sorry in advance, I’ve tried to read a lot of this thread previously, but haven’t got through it all. So if it’s already been discussed, apologies!

Hope that helps and thanks!

-Daniel

---

## #420 **Mica** (@paperdigits) · 2025-10-30 04:54

Oh, that looks like a cool project, but I don’t think this thread is about that software, but a different software called agx-emultion

---

## #421 **jo** (@hanatos) · 2025-10-30 08:11

> **@RTLdan** (帖子 #419):
> I’m currently experimenting with Spectral Film Lut from Jan Lohse

oh nice, there’s b/w stock too!

---

## #422 **Olli** (@okke) · 2025-10-30 09:40

Interesting project as well even if different. But the point still stands somewhat, the contrast can be a bit much. With the vkdt implementation, I have to quite often raise the exposure, try to fiddle with the parameters but also (locally or globally) lift shadows often before the filmsim node.

---

## #423 **jo** (@hanatos) · 2025-10-30 09:56

maybe post a concrete example, maybe as a playraw?

---

## #424 **** (@mikae1) · 2025-10-30 12:40

> **@RTLdan** (帖子 #417):
> I found out about this Project from Nico at Demystify color. I’m sure you will be seeing a lot more people come in from there!

Cool.

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 Where did he mention agx-emulsion? Not finding anything on [his channel](https://www.youtube.com/@demystifycolor/videos).

> **@RTLdan** (帖子 #419):
> I’m currently experimenting with Spectral Film Lut from Jan Lohse (GitHub - JanLohse/spectral_film_lut: Generate LUT for film emulation based on film datasheets.).

Interesting! A Python project. I wonder how difficult it would be to build an .AppImage.

I know this isn’t a darktable thread, but sadly the LUT 3D module in darktable [rather limited](https://discuss.pixls.us/t/linear-to-log-for-film-emulation-in-darktable-are-1d-luts-possible/40847). But perhaps it would be possible to create LUTs in [Spectral Film LUT](https://github.com/JanLohse/spectral_film_lut) that could be used in darktable?

Also, the grain module is monochrome only in darktable and grain gets applied pre-interpolation.

---

## #426 **Olli** (@okke) · 2025-10-31 09:06

I’ll try to find some when I have the time. Though often the case is e.g. faces partly in shadow going too dark so I’ll have to find something else.

---

## #427 **jo** (@hanatos) · 2025-10-31 10:54

nice, thanks. you can also share privatly with me if you’re more comfortable with that. i’m not in the business of selling images…

sometimes it’s a matter of juggling print and film exposure, sometimes i find i’m just so used to digital dynamic range that film (sim) appears to be limiting. but i want to make sure i understand your issue exactly.

---

## #428 **** (@niklasiivari) · 2025-10-31 18:30

I have found that the *zones* module is quite helpful when I feel like the shadows get too dark. It often results in more natural results compared to curves + drawn masks.

---

## #429 **nosle** (@nosle) · 2025-10-31 19:29

So continuing the discussion about tint etc from above. The recent spectral film simulation in ART gave me the opportunity to compare. Note that I’m not expecting the looks to be the same but I think it illustrates the tint issue quite well. Additionally I don’t remember my first tests with AGX filmsim to be this tinted.

vkdt

[[![2025-10-31-202514_1193x1009_scrot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/6/f6acec26c0e3f77c841aaff51075bc13821235c2_2_690x583.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/6/f6acec26c0e3f77c841aaff51075bc13821235c2_2_690x583.png)

2025-10-31-202514_1193x1009_scrot1193×1009 1.09 MB](/uploads/short-url/zcbWqBIAwaEmm1ss4g4ekBn94hc.png?dl=1)

ART

[[![2025-10-31-203020_1372x817_scrot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/d/7dc14f71757b6a0c96b260f85ee0dff6f1d83057_2_690x410.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/d/7dc14f71757b6a0c96b260f85ee0dff6f1d83057_2_690x410.png)

2025-10-31-203020_1372x817_scrot1372×817 1.15 MB](/uploads/short-url/hWtQEAbkOeeC2pwWW2V7LkPOWt9.png?dl=1)

The latter look is what I’d expect from Portra 160 having shot it a fair bit.

---

## #430 **jo** (@hanatos) · 2025-11-01 18:37

there may have been something wrong with the optimiser that matches the white balancing during printing. now there’s a bug in <s>hyprland</s> libdecor, hence the right image is stretched.

left: agx-emulsion original python, right vkdt (portra 160, supra endura).

[[![20251101_19h32m05s_grim](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/3/d39f481fc928fa4bb5b611c695031996687cf138_2_690x397.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/3/d39f481fc928fa4bb5b611c695031996687cf138_2_690x397.png)

20251101_19h32m05s_grim2175×1254 2.32 MB](/uploads/short-url/uc60mkf3VSDqv9zlMrCvXPCiaqk.png?dl=1)

i’ll need to make sure it does now what it’s supposed to and then re-run the wb script.

---

## #431 **Olli** (@okke) · 2025-11-02 08:31

Now looking again at the set where I recently had troubles I think I know what the main problem was: I was comparing to darktable which is adding some automagic exposure and counters the exposure compensation as well. When disabling the exposure compensations and setting e.g. sigmoid contrast to 2.0, the situation is quite similar. The vkdt default tone curve just has so little contrast in comparison that the exposure difference is not so visible. The dynamic range / contrast with filmsim is just a bit limiting so some selective exposure or zone usage is often needed. Or fiddling with the parameters in film sim, but those are not orthogonal and need to be adjusted a bit back and forth (skill issue as well).

Good to hear that the WB is potentially seeing changes, been having some trouble with that as well. I’ll check with the latest changes and see if there’s some case where a playraw would be interesting (due to contrast or wb).

---

## #432 **Anna** (@betazoid) · 2025-11-02 09:22

I think I did mention the wb bug here, didn’t I?

---

## #433 **** (@Thomsen) · 2025-11-02 13:17

I’ve also experienced problems with managing the contrast in VKDT. Reducing contrast is always more difficult to do in a pleasing way than adding contrast. It does seem like the default contrast curve in VKDT is stronger than agx, when looking at your example here.

> **@hanatos** (帖子 #430):
> 20251101_19h32m05s_grim2175×1254 2.32 MB
20251101_19h32m05s_grim2175×1254 2.32 MB

In addition to the default contrast, I also remember reading about the preflash-method in AGX being left out in VKDT. This seems like a great way of managing the contrast in high-contrast images. Perhaps it is work a re-visit?

> **@arctic** (帖子 #15):
> Regarding preflashing I have a very good example from a Play Raw High contrasts in a man made wilderness, from @Popanz.
Print paper has limited latitude and predefined contrast, while film negatives can capture a very large dynamic range (easily 10+ stops). Preflashing is a simple hack of the printing process to retain some of the highlight details. Print paper is essentially flashed with some light before the negative projection, i.e. making it more gray-ish and taming down the highlights (have a look at this video for a real life example https://www.youtube.com/watch?v=lcx4ag7iygI). The price to pay is reduced contrast and saturation.
garden_pro_400h_crystal_archive_typeii_1.0cpl_0preflash_0Y0M_015pe1999×1334 5.14 MB
garden_pro_400h_crystal_archive_typeii_1.0cpl_001preflash_0Y0M_015pe1999×1334 5.07 MB

---

## #434 **jo** (@hanatos) · 2025-11-03 07:57

> **@okke** (帖子 #431):
> I’ll check with the latest changes

this is pushed now:

[[![grim](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/2/d290d95e67db9420cef8e8d0717130875bfe06f8_2_690x360.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/2/d290d95e67db9420cef8e8d0717130875bfe06f8_2_690x360.png)

grim3046×1590 2.64 MB](/uploads/short-url/u2KBBAwSoUdMMXaWXu0OqP0JMTK.png?dl=1)

> **@betazoid** (帖子 #432):
> I think I did mention the wb bug here, didn’t I?

i don’t remember that. but it’s possible that i would have ignored text if you didn’t show this with pictures. i’m a visual person…

> **@Thomsen** (帖子 #433):
> In addition to the default contrast, I also remember reading about the preflash-method in AGX being left out in VKDT. This seems like a great way of managing the contrast in high-contrast images. Perhaps it is work a re-visit?

right, certainly not out of scope

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 not sure where the contrast difference came from though. there is no other curve involved in the two images. maybe it was a slight exposure difference that pushed values to a different slope in the film response curve.

---

## #435 **Daniel Rheaume** (@RTLdan) · 2025-11-03 20:05

Sorry for the delay!

The Demystify Color reference is probably behind a paywall. I’m a subscriber, so I can’t see what’s free vs paid. He’s mainly approaching this as a Resolve colorist. The series is ongoing. AGX Emulsion only got a brief mention in Part 1, but he compared AGX Emulsion and Spectral Film LUTs to the new Genesis plugin, which has been intentionally withholding about how it works. The hunch is that Genesis is also using spectral methods.

On my contrast issue, part of it might’ve been the stock I was testing (5207/2383). Other stocks have felt more manageable. That said, contrast still skews high for me overall. My best results I’ve got so far come from a little pre-emulation shaping, and a post-emulation node to rein in print contrast. The drawback to post emulation contrast trim is that once highlights/shadows have gone through the LUTs, that post node has a hard time pulling back shadow or highlight detail. Like you would expect, it’s like trying to undo a print. But if I put too much pre emulation contrast trim, I’m concerned I’m affecting too much what the input into the negative film emulation is expecting, giving it an anemic quality.

Two questions I’m still stuck on -

1. AGX Emulsion in a Resolve video workflow:
 Has anyone actually exported LUTs from AGX Emulsion? I tried to make it happen with ChatGPT and command line, but hit a wall. I’m not a coder, but I can run command line tools okay with directions. Is LUT export even feasible with the current implementation? Ideally, I’d love separate LUTs for the negative and the print stages, much like Spectral Film Luts is doing, or is that out of scope right now? I really like the level of detail in AGX and it looks like it would be a more advanced tool than SFL currently is.
2. Tone mapping expectations for film emulations in Resolve
 In Resolve, I’m converting camera → DWG/DI for processing, then DWG/DI → display. My monitoring is Rec.709 / gamma 2.4, calibrated, but set to 200 nits, because I’m not working in a dim room very often. The color space transform tools gives a few tone mapping options for log→display. ChatGPT suggested explicitly setting a 100-nit max input mapping because it assumed that matches the film emulation’s intent. I’ve setup Spectral Film LUTs output to DWG/DI, but they still have some internal assumption about scene vs display mapping and it’s undocumented as far as I could find. I’ll probably try to reach out to the developer soon.

However, generally speaking, does anyone know what these emulations expect in terms of display referred tone mapping? Should we be aiming at a strict 100-nit assumption on the display side, or does the math expect something else (especially if monitoring at 200 nits)?

Thanks again for working on such a cool project!

---

## #436 **** (@mikae1) · 2025-11-03 23:09

> **@RTLdan** (帖子 #435):
> Is LUT export even feasible with the current implementation?

Open a Hald CLUT identity file in agx-emulsion and just process that file and export it. You can then convert the Hald CLUT to cube. There used to be a script for this at [https://github.com/sobotka/hald2cube](https://github.com/sobotka/hald2cube)

Perhaps there are other options. If not, perhaps that LLM would be willing to assist you.

There’s an identity file [here](https://rawpedia.rawtherapee.com/index.php?title=File:Hald_CLUT_Identity_12.png).

But you probably want to generate an own identity file with a wider color space than sRGB. Here’s what it looks like for sRGB according to [RawPedia](https://rawpedia.rawtherapee.com/Film_Simulation):

```
magick hald:12 -depth 16 -colorspace sRGB hald12_16bit.tif

```

I replaced `convert` with `magick`, because that’s how it works these days.

---

## #437 **Daniel Rheaume** (@RTLdan) · 2025-11-03 23:15

Thank you! That’s a super interesting idea! I’ll have to look into using the hald image!

---

## #438 **jo** (@hanatos) · 2025-11-04 07:48

…just to add to that, keep in mind to disable autoexposure/glare/halation/couplers, because these are not per pixel but act on at least a local environment.

---

## #439 **** (@Christian-B) · 2025-11-04 08:30

> **@mikae1** (帖子 #436):
> You can then convert the Hald CLUT to cube. There used to be a script for this at https://github.com/sobotka/hald2cube

This link seems to be dead, but here’s another interesting article.
<aside class="onebox allowlistedgeneric" data-onebox-src="https://marcrphoto.wordpress.com/2025/08/11/diy-png-to-cube-converter/">
 <header class="source">


[![图片448](https://d2x313g9lpht1q.cloudfront.net/original/3X/a/d/add855b0e0c036829cc730447c58ba4d8f194197.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/a/d/add855b0e0c036829cc730447c58ba4d8f194197.png)

 [Open Source Photography – 11 Aug 25](https://marcrphoto.wordpress.com/2025/08/11/diy-png-to-cube-converter/)
 </header>

 <article class="onebox-body">


[![图片449](https://d2x313g9lpht1q.cloudfront.net/original/3X/7/f/7f8512d58bcca671a41d92d15a7cdf31f348e359.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/7/f/7f8512d58bcca671a41d92d15a7cdf31f348e359.jpeg)

### [DIY PNG to Cube Converter](https://marcrphoto.wordpress.com/2025/08/11/diy-png-to-cube-converter/)


5 minutes read time 🎬 From PNG to .CUBE – Take Full Control of Your Film Simulations So, you’ve created a killer film look in RawTherapee, ART or anything else that spits out PNGs. You’re happy. It…

 </article>









</aside>

Greetings from Brussels,

Christian

---

## #440 **Todd Prior** (@priort) · 2025-11-04 15:13

<aside class="onebox allowlistedgeneric" data-onebox-src="https://www.color.io/free-online-lut-converter">
 <header class="source">


[![图片450](https://d2x313g9lpht1q.cloudfront.net/original/3X/6/f/6f49657a50f195fc9b751181382af7bcaac6db3d.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/6/f/6f49657a50f195fc9b751181382af7bcaac6db3d.png)

 [color.io](https://www.color.io/free-online-lut-converter)
 </header>

 <article class="onebox-body">


[![图片451](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/4/a4da2eb2e46096b7f7aad08497f1254b6e09f8af_2_690x430.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/4/a4da2eb2e46096b7f7aad08497f1254b6e09f8af_2_690x430.jpeg)

### [Free Online LUT Converter And Previewer | Color.io](https://www.color.io/free-online-lut-converter)


Preview and convert 3D LUTs for most applications, cameras, game engines and more with the free color.io 3D LUT converter that runs directly in your browser.

 </article>









</aside>

---

## #441 **Ryan Cara** (@Ryan_Cara) · 2025-11-08 03:14

> **@mikae1** (帖子 #436):
> wha

Would love to be updated on this! The colourspace of a HALD confuses me. I’ve been trying to convert some AGX emulsion looks to LUT’s and haven’t been very successful.

---

## #442 **Yogansh Bhatt** (@Yogansh_Bhatt) · 2025-12-18 14:40

Not only photography but because VKDT supports MCRAW, I and a few others have started finding immense value in Your project! It is fascinating and almost feels like magic…addicted at this point!

Thank you very much for creating THIS!

---

## #444 **Aurelien** (@Aurelien_05) · 2026-02-22 14:52

Hello, I happened to come across this thread while searching for articles on film simulation. Thank you so much for creating this; the final results are truly beautiful and stand out from other film simulation apps I’ve used. Like many other members here, I hope you will continue to dedicate time to further perfecting this project.

I’ve spent the past week reading through over 400 comments in this topic and experimenting with some of my own images. I am a Mac user with absolutely no knowledge of Python. This is also my first time installing Darktable and ART—which I did specifically to try out the AgX emulation after reading this post. I’ve looked through comments from other Mac users, but I still have a few unanswered questions and would appreciate help from the creator and the community.

1. First, I’d like to confirm the required state of the input image. From what I’ve gathered, it should be a 16-32 bit TIFF or EXR in a Linear ProPhoto or Rec 2020 color space. Am I correct in assuming that no Sigmoid, Filmic, or Base-curve transforms should be applied?

[[![save darkable](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/9/9908db491e13e072435af8535c598e6592da7094_2_690x316.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/9/9908db491e13e072435af8535c598e6592da7094_2_690x316.jpeg)

save darkable2048×939 295 KB](/uploads/short-url/lPO1K6zY8yEIRTUyjT5Xd1unNVW.jpeg?dl=1)

> **@ZeroEcks** (帖子 #115):
> The only issue I noticed that stood out was using the agx_emulsiom GUI, being uncolour managed, on macos gives significantly different gamma / contrast when saving a layer compared to the viewing window. Unfortunately this is a bit of a blocker for actually using it much, but it’s somewhat fixable with adjusting the black point and contrast afterwards.

> **@NateWeatherly** (帖子 #56):
> On a Mac, just having an ImageP3 or DisplayP3 output ICC profile would come pretty close to having a color managed preview.

> **@arctic** (帖子 #122):
> Also I am not super keen at having this as a final solution. I think there are much better human interfaces in other softwares (vkdt, darktable, rawtherapee, art…), so there is probably no need to rebuild everything. I see this as a tech demo that I am very comfortable at hacking, and go crazy with details. If it is going to be a viable solution for actual doing some work I could put together something better in the future. For now my focus has been the engine and the “look”. But thank you for the critic! It is in my mind.

Regarding my setup on Mac: I am using “Output Color Space = Display P3 or DCI P3” in Napari. The images after “Save Layers” are often significantly desaturated compared to what is displayed in the Napari viewer. I also really like the sliders in the Layer Controls—they produce great results in the preview and are very convenient for adjusting contrast and gamma. However, when I “Save Layers,” those adjustments are not applied to the final image; they seem to only affect the Napari interface.

Has anyone found a fix for this? I’ve been struggling with this for days because the colors look perfect in Napari, but the exported result is completely different. Is this a Mac-specific issue, or do Windows users experience this as well? Could this be an installation error on my part? How can I fix this?

[[![run](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/a/0a1d6efad388872b34d9363cce3901b4200e13c2_2_690x578.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/a/0a1d6efad388872b34d9363cce3901b4200e13c2_2_690x578.jpeg)

run2048×1718 557 KB](/uploads/short-url/1rtPOvgCRQdqA8bjXHDLmruqW8W.jpeg?dl=1)

[[![export](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/a/ca3b2c010e9885be7f600603a854962407ec88f8_2_690x399.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/a/ca3b2c010e9885be7f600603a854962407ec88f8_2_690x399.jpeg)

export2048×1185 840 KB](/uploads/short-url/sR1dTUz0kuhWGXWW5nNHuVl5AXm.jpeg?dl=1)

<ol start="3">
<li>After exporting an image from Darktable and loading it into Napari via the filepicker, the image looks very different. It appears extremely high-contrast, with crushed shadows and blown-out highlights. I’m not sure if this affects the final result after clicking “Run.” Is this normal behavior, or am I doing something wrong?</li>
</ol>

[[![raw export Darkable](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/2/b25d04a4bd1db08d3bd658621fd562b85ee32daa_2_690x511.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/2/b25d04a4bd1db08d3bd658621fd562b85ee32daa_2_690x511.jpeg)

raw export Darkable2050×1520 760 KB](/uploads/short-url/prShn1sgg2M7MCdGkLob0BN8EXg.jpeg?dl=1)

[[![load pics](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/b/7b79f05034460a70d4d6691d663594c0566ea949_2_690x704.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/b/7b79f05034460a70d4d6691d663594c0566ea949_2_690x704.jpeg)

load pics2502×2556 789 KB](/uploads/short-url/hCjYQppsSbtA4ZImcS8eJnIJRMt.jpeg?dl=1)

<ol start="4">
<li>I’ve noticed people often use AgX Emulsion with vkdt or ART . Can I use it directly with RAW files, or do I still need to export the RAW to a Linear ProPhoto RGB file first?

I’ve been trying to get “agx_emulsion” working in ART for a few days now. Although the option appears in ART, the effect doesn’t seem to work—moving the sliders or changing the film simulations results in no visual change to the image. Have any Mac users successfully resolved this? I would appreciate a brief guide.</li>
</ol>

[[![Screenshot 2026-02-22 at 21.50.43](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/8/68ddcfc931b5553fb726ca177b953de6a07bc84d_2_690x453.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/8/68ddcfc931b5553fb726ca177b953de6a07bc84d_2_690x453.png)

Screenshot 2026-02-22 at 21.50.433154×2074 2.34 MB](/uploads/short-url/eXGSWE769ITNFwjesuFjiPLg5lj.png?dl=1)

<ol start="5">
<li>My primary workflow has always been in Capture One or Lightroom Classic . Is there a way to export a file with a Linear ProPhoto RGB profile from C1 or LrC that is equivalent to the output from Darktable?</li>
</ol>

Thank you in advance for your help!

---

## #445 **** (@tankist02) · 2026-02-22 22:16

In the last screen shot the Color/Tone Correction tool is not turned on (the symbol to the left of the name).

---

## #446 **** (@lambda) · 2026-02-22 22:46

This is such an awesome work! I hope this comes mainline Darktabel.

---

## #447 **Georg N** (@geni1105) · 2026-02-23 10:59

In vkdt AgX Emulsion is built-in as “filmsim” node, see [vkdt: filmsim: artic's sophisticated spectral analog film simulation saturation with DIR couplers the filmsim data](https://jo.dreggn.org/vkdt/src/pipe/modules/filmsim/readme.html)

It can be applied directly to raw images, in fact that’s the default way to use it, as it replaces the filmcurv module.

---

## #448 **None** (@sahuaro.senorita) · 2026-02-23 16:41

> **@Aurelien_05** (帖子 #444):
> I am a Mac user with absolutely no knowledge of Python.

that makes two of us! how did you get this to run on your mac? a few weeks ago i spent a couple days trying to get it to run & troubleshooting to the best of my ability but gave up after it seemed like newer versions of mac maybe broke compatibility.

---

## #449 **Aurelien** (@Aurelien_05) · 2026-02-24 02:35

I ran into some errors during the initial installation. I ended up copying the error messages from the Terminal and pasting them into ChatGPT to find a solution.

---

## #451 **** (@Cristian) · 2026-02-24 10:10

I used agx-emulsion in the last few days and my conclusion is: this is outstanding, great work! The best film simulation apps I’ve used, keep up the great work. This is my favorite after I had tried so many presets, luts, and other softwares like DXO FIlmpack. I can only hope this will be integrated as a module in Darktable.

---

## #452 **** (@mikae1) · 2026-02-28 15:24

> **@Cristian** (帖子 #451):
> this is outstanding, great work! The best film simulation apps I’ve used

I wholeheartedly agree. It’s *the* best for stills photography.

> **@Cristian** (帖子 #451):
> keep up the great work.

The project was last updated 11 months ago, so I wouldn’t get my hopes up. I don’t know if [@agriggio](/u/agriggio) and [@hanatos](/u/hanatos) are continuing to develop it for ART and vkdt.

> **@Cristian** (帖子 #451):
> I can only hope this will be integrated as a module in Darktable.

Same here! It’s a question of performance, but [@hanatos](/u/hanatos) showed that GPU acceleration could do *a lot* for performance. It’s snappy in vkdt!

---

## #453 **jo** (@hanatos) · 2026-02-28 15:46

… well i am fine tuning stuff in vkdt, such as more controllable couplers and halation. still features missing (mainly preflash i think).

vkdt’s gpu pipeline is very different from darktable’s. sorry for how i designed dt’s pipe in the past, seemed like a good idea then. even without all the cpu fallback/copy code there’s a lot of cpu sync and overall just so much that hasn’t been designed for really fast execution/new hardware. not sure how snappy that can be, it’s a lost fight. on the bright side it’s well compatible with the hardware from back when, and the cpu codepath makes it more accessible to contributors.

---

## #455 **Yogansh Bhatt** (@Yogansh_Bhatt) · 2026-03-17 07:32

[[![Screenshot_20260317-125950](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/0/f09af13610244ecf8543ba4f535b414d66779e3d_2_449x1000.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/0/f09af13610244ecf8543ba4f535b414d66779e3d_2_449x1000.png)

Screenshot_20260317-1259501344×2992 65.8 KB](/uploads/short-url/ykuypPyYS6N4l40dcthVZoGOjJX.png?dl=1)

Not sure how it will work but hopefully I’ll be able to test out kodachrome64 my beloveth soon : )

---

## #456 **jo** (@hanatos) · 2026-03-17 08:13

whoa nice! positive film and lots of refactoring going on.

---

## #457 **Yogansh Bhatt** (@Yogansh_Bhatt) · 2026-03-17 09:03

After a LONG hiatus he seems to be back! And as soon as he is back he adds positive film!

I’m sure next up is some B&W.

Can’t wait!

Also an unrelated question, all my photos seem to be very warm after d65 conversion and I either use the channels in color module or pick preset and finding something neutral to get started with filmsim. Is this normal?

A bunch of them are RAWs from Fuji x-h2s, some RAWs from my pixel. I almost always need to make WB adjustments at which point I feel like I’m Messing up the input to the filmsim module . I tried also adjusting the y and c filters to get it to a nice place instead using the color module (assuming it must stay 1-1-1 for the sake of d65 input) but it’s not convenient…not sure what I am doing wrong but hopefully you can shed some light!

---

## #458 **** (@mikae1) · 2026-03-17 11:45

Nice catch

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 I’m so thankful for every little line of code added to this fantastic project. Will you likely add the positive films to vkdt, [@hanatos](/u/hanatos)?

---

## #459 **jo** (@hanatos) · 2026-03-17 11:53

> **@Yogansh_Bhatt** (帖子 #457):
> Also an unrelated question

maybe open a separate thread and post some images? i understand much faster if i see pictures

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

the filters in the filmsim module are optimised to yield d50 neutral iirc, and should be identical to the original agx-emulsion python.

> **@mikae1** (帖子 #458):
> Will you likely add the positive films to vkdt, @hanatos?

absolutely. have to understand what are the changes and remember how to ingest the .json.

---

## #460 **** (@mikae1) · 2026-03-17 11:56

> **@hanatos** (帖子 #459):
> absolutely. have to understand what are the changes and remember how to ingest the .json.

Cool, thanks!

[![:slightly_smiling_face:](https://discuss.pixls.us/images/emoji/apple/slightly_smiling_face.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slightly_smiling_face.png?v=12)

[![:+1:](https://discuss.pixls.us/images/emoji/apple/+1.png?v=12)](https://discuss.pixls.us/images/emoji/apple/+1.png?v=12)

---

## #461 **** (@CarVac) · 2026-03-17 12:01

This is a really cool project! It’s almost the complete opposite of Filmulator, which primarily concerns itself with the control of diffusion/depletion effects and specifically avoids mimicking grain or specific films’ colors. (because its goal is different: quick and easy decision-making while editing)

> **@arctic** (帖子 #256):
> I am pretty sure that there are chemical/diffusion effects that we are not considering. For example, there can be local effects on the concentration of developer, that is depleted by the high density areas, and in my mind would act as inhibition.

---

## #462 **** (@Cristian) · 2026-03-17 12:01

This is great, I’m glad for the positive films update and for the continuity of this project. Hope to see some b&w film in the future.

---

## #463 **Yogansh Bhatt** (@Yogansh_Bhatt) · 2026-03-17 12:03

thanks, will do! I also have many other favours to ask in terms of workflow advice.

---

## #464 **** (@mikae1) · 2026-03-17 20:34

> **@CarVac** (帖子 #461):
> This is a really cool project! It’s almost the complete opposite of Filmulator, which primarily concerns itself with the control of diffusion/depletion effects and specifically avoids mimicking grain or specific films’ colors. (because its goal is different: quick and easy decision-making while editing)

It was a long time since I checked out Filmulator. I always liked the idea, but never found the results to be filmlike (despite the name). I wish it was a bit like Film Look Creator in DaVinci Resolve. It does not attempt to emulate any specific film, but to emulate filmlike properties (like halation, color grain, film like color etc.).

---

## #465 **** (@CarVac) · 2026-03-17 20:50

I liked the results of shooting film, always finding a simple curve applied to the lab scan to look quite good, but I was never enamored with the technical flaws like halation and grain. So I chose to simulate aspects of the development process to achieve only the improvements that I care about.

I guess the name Filmulator is misleading for those looking for filmlike looks, but SimpleBetterJPEGifier (a more precise description of what it achieves for me) doesn’t really roll off the tongue.

Maybe there’s some better messaging I can put on the website?

---

## #466 **** (@Thomsen) · 2026-03-21 13:33

Testing out the filmsim on some aurora shots!

[[![Nordlys 1](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/8/788047d78136dc4b67176aa45b7b566ab6fb4e69_2_690x458.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/8/788047d78136dc4b67176aa45b7b566ab6fb4e69_2_690x458.jpeg)

Nordlys 14416×2936 19.3 MB](/uploads/short-url/hc08stC3AS41HCFOm4qudMorHZf.jpeg?dl=1)

[[![20260321_Stockholm_0000](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/a/4a283da7581a539e16b7d3ab047c770e69060d1f_2_494x750.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/a/4a283da7581a539e16b7d3ab047c770e69060d1f_2_494x750.jpeg)

20260321_Stockholm_00002913×4416 3.99 MB](/uploads/short-url/aA1y041FI3xUZd3KFEpTO78KhMb.jpeg?dl=1)

And a timelapse video:
<aside class="onebox allowlistedgeneric" data-onebox-src="https://e.pcloud.link/publink/show?code=XZ0M1GZTKa7stdpbX8aJ5a47TmvNbcG4N07">
 <header class="source">


[![图片465](https://d2x313g9lpht1q.cloudfront.net/original/3X/d/d/dd87d6a17000924d83c83021f22bd98fe9d38b30.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/d/d/dd87d6a17000924d83c83021f22bd98fe9d38b30.png)

 [pCloud](https://e.pcloud.link/publink/show?code=XZ0M1GZTKa7stdpbX8aJ5a47TmvNbcG4N07)
 </header>

 <article class="onebox-body">


[![图片466](https://d2x313g9lpht1q.cloudfront.net/original/3X/f/0/f0af0bf6a23181dcca305babab1bd95ecc9389fa.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/f/0/f0af0bf6a23181dcca305babab1bd95ecc9389fa.jpeg)

### [Aurora timelapse filmsim.mov - Shared with pCloud](https://e.pcloud.link/publink/show?code=XZ0M1GZTKa7stdpbX8aJ5a47TmvNbcG4N07)


Store videos in pCloud. Share them with just the right people. Access them on any device. Create a free account now!

 </article>









</aside>

---

## #467 **Upperechelonstr8up** (@upperechelonstr8up) · 2026-03-28 04:22

Something i would be very impressed to see from this project in the future is the recreation of old technicolor/eastmancolor/film from the 1990s - backward. I have never seen a film emulation tool **(or really modern film in general)** emulate that imperfect and almost **oil painting** like quality, and I have been searching for years on a way to accurately emulate it with very little success since every film emulation plugin/filter is simply concerned with changing the color relationships. Which to me has always just looked like digital with color correction and in my opinion looks just the same as everything else. **It has to be possible some how, right?** I hope you all understand what i’m talking about, it’s that kind of painted look that must’ve been a result of the photo chemical process not being as refined and perfected as it is nowadays, where subjects from a distance can almost bleed into smudges on the frame. When movies and color photography didn’t look real, didn’t look synthetic, but gave off the appearance of moving paintings. For everything that i have seen in my research on this topic, this tool has gotten the closest I’ve seen so far (but still not quite there). I am probably the least tech literate person in this entire thread and have never even picked up a film camera before so please tell me your guys’ thoughts on this.

---

## #468 **Terry Pinfold** (@Terry) · 2026-03-28 09:35

> **@upperechelonstr8up** (帖子 #467):
> emulate that imperfect and almost oil painting like quality

Slightly off topic response from me. I grew up with film and made a career out of shooting and processing film. I have no desire to return to a film like look as I embrace the digital image for its own sake. However, I often wish to give my image more of a painted looked. That could be a water color effect or an oil painting look. That is one emulation I would like to see.

---

## #469 **** (@Cristian) · 2026-03-28 09:56

Interesting, I’m intrigued by this oil painting look; I’d love to be able to apply it, at least partially, to a digital photograph. Can you show us some examples of film photos that have this look?

---

## #470 **Upperechelonstr8up** (@upperechelonstr8up) · 2026-03-28 15:20

Hey, my account will only let me post 4 images per post so I’ll be responding in a thread. Sorry for the inconvenience.

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/d/1d35126ce5a9248bae8f516d344ebfd074bb4b45_2_690x288.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/d/1d35126ce5a9248bae8f516d344ebfd074bb4b45_2_690x288.jpeg)

image1443×604 113 KB](/uploads/short-url/4anyh3frmvlG31gq3fsjENSjsb3.jpeg?dl=1)

First, here’s an image from a newer movie shot on film. Now i think this looks good don’t get me wrong, but i feel that newer film looks too perfect and too similar to digital. Now here’s a few examples of what I’m talking about.

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/7/b7f4add80a4e2fa79e7dc54e1a03b654c849b83f_2_690x291.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/7/b7f4add80a4e2fa79e7dc54e1a03b654c849b83f_2_690x291.jpeg)

image1460×617 146 KB](/uploads/short-url/qflBaR8iSE9sGQUH2lGC6Ri2yrZ.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/9/198ecc04966799b60c4b2479b88fcb63722b3758_2_690x289.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/9/198ecc04966799b60c4b2479b88fcb63722b3758_2_690x289.jpeg)

image1459×612 199 KB](/uploads/short-url/3E5Sqhuctvo2PdmS39xqf7xrUus.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/4/545a035e13fcca4d10fa17fd4343f0e84f54d5d5.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/4/545a035e13fcca4d10fa17fd4343f0e84f54d5d5.jpeg)

image824×445 68.3 KB](/uploads/short-url/c2cXvvUsHej51Dn8AFsDU8Vg1y5.jpeg?dl=1)

---

## #471 **Upperechelonstr8up** (@upperechelonstr8up) · 2026-03-28 15:21

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/3/6365e7a5c59569ec71268956bd84ed77bbb861c3_2_690x388.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/3/6365e7a5c59569ec71268956bd84ed77bbb861c3_2_690x388.jpeg)

image1600×900 328 KB](/uploads/short-url/ebjBbtdTlvZkZuXlIOTTrz5nSPp.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/3/f36f4c3385e6d5beb87cbc58686bc3412982547e_2_690x388.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/3/f36f4c3385e6d5beb87cbc58686bc3412982547e_2_690x388.jpeg)

image1600×900 291 KB](/uploads/short-url/yJwtJ2ngYZs5aOeh4kLUyDvgmWa.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/0/6020e6435a2d30163a020ec4837ee3485d68b4af_2_690x388.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/0/6020e6435a2d30163a020ec4837ee3485d68b4af_2_690x388.jpeg)

image1600×900 260 KB](/uploads/short-url/dIok5evvaI0mbAZQNKxt3FcFljF.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/3/d3edd8a0db1375ea5fc62612e674166cda26c910_2_690x500.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/3/d3edd8a0db1375ea5fc62612e674166cda26c910_2_690x500.jpeg)

image1073×779 193 KB](/uploads/short-url/ueOkqf40nabcVpyTKti7NQp7Dsk.jpeg?dl=1)

Even a movie with less visible grain like Singing In The Rain, still is able to give a certain softness that modern film and especially digital lacks.

---

## #472 **Upperechelonstr8up** (@upperechelonstr8up) · 2026-03-28 15:21

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/2/626eada7206dbd5bf016b7e74f777c238f054a64_2_690x313.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/2/626eada7206dbd5bf016b7e74f777c238f054a64_2_690x313.jpeg)

image1920×872 84.5 KB](/uploads/short-url/e2LUZVmYrIOy00SdlZsFvRUKEte.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/3/0330e43881af25d0db07d5f21eb9700418ee5560.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/3/0330e43881af25d0db07d5f21eb9700418ee5560.jpeg)

image800×320 96.4 KB](/uploads/short-url/sebhniXR6JOmfJeCvJ8YDB2iUE.jpeg?dl=1)

It seems that the switch between these looks occurred around 2008 - 2010. In fact, there is a Tarantino movie from 2007 which is one of the last examples of a movie being able to accurately create this look.

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/d/0d3acd94500c1be3265a4a7aeccc913023efd0cd_2_690x291.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/d/0d3acd94500c1be3265a4a7aeccc913023efd0cd_2_690x291.jpeg)

image1394×588 118 KB](/uploads/short-url/1T2bUgCCBG2ZePmOY9BhFBjjpff.jpeg?dl=1)

And it’s not the dust and scratches. Infact, i think the dust and scratches are one of the least important elements to this style.

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/c/2c7ae57f97c66e0a4fc5b3046c507aafaae3dcb4_2_690x296.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/c/2c7ae57f97c66e0a4fc5b3046c507aafaae3dcb4_2_690x296.jpeg)

image1393×599 207 KB](/uploads/short-url/6lujpTUOPjsoPclvlvNRE8HPEiw.jpeg?dl=1)

---

## #473 **upperechelonst9up** (@upperechelonst9up) · 2026-03-28 15:30

Hello, same guy here. I had more examples as well as examples of the difference of newer film, but pixls.us only let me reply 3 times. If you need more context, i will be happy to rewrite my response.

---

## #474 **Nuno Paulino** (@hatsnp) · 2026-03-28 17:14

Keep in mind that a lot of these scans were done with older technology and may not represent accurately what was shown in the cinemas and what a good modern scan, which is more faithful to the final product, will look like.

Also I don’t think your comparison is fair. One battle after another had a lot of shots in direct sunlight which would be a better comparison vs for example the good, the bad and the ugly.

---

## #475 **** (@Cristian) · 2026-03-28 17:30

Thank you, I understand perfectly now what look are you talking about. Yes, I agree with you, these shots are great I mean look at those colors how beautiful they are, some people may call them muted. I remember when I was a novice in editing my photos I cranked up the saturation slider to get more “vibrant” colors

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 I’m glad I’m past that.

Have you seen this? [https://www.youtube.com/watch?v=za20Kb2VSN8&t=504s](https://www.youtube.com/watch?v=za20Kb2VSN8&t=504s)

I think you may find it interesting.

Also you should read this book: [LIFELIKE: A book on color in digital photography – Dehancer Blog](https://blog.dehancer.com/lifelike-book/)

---

## #476 **Upperechelonstr8up** (@upperechelonstr8up) · 2026-03-28 17:40

In my original example before i got cut off i actually did use both shots from magnolia and OBAA (both directed by PTA) as a distinction between how new and old film looks.

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/9/c9ac29166682ea51bcec81f3332574e97df231e3.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/9/c9ac29166682ea51bcec81f3332574e97df231e3.jpeg)

image1024×424 65.8 KB](/uploads/short-url/sM4P4p1gNa28J4u9g0lLUBAM351.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/3/5/3529b71484779bdda8ba4803cacd5bbd100c5fc6.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/3/5/3529b71484779bdda8ba4803cacd5bbd100c5fc6.jpeg)

image1024×536 104 KB](/uploads/short-url/7AiGaRs9LWmh4SEhO1o464ZWQoC.jpeg?dl=1)

Also most of the scans i sent were from 4k re-releases, but i do think part of the appeal of this look is due to how the celluloid has aged over time. Still, the difference between modern film and film before 2009-2008 is clear.

---

## #477 **Upperechelonstr8up** (@upperechelonstr8up) · 2026-03-28 17:50

I will look into these! However, i think the colors while they are very beautiful and miles ahead most modern cinematography isn’t what sells this look. Rather it’s the way these colors blend into each other and spill over the edges in a both organic and imperfect way. There are modern movies that have good color palettes as the classics that still fail to achieve this special kind of quality. Personally, i don’t really understand the point of shooting on film nowadays if it’s just gonna look akin to an arri alexa.

---

## #478 **Nuno Paulino** (@hatsnp) · 2026-03-28 18:19

This just seems like an editing decision of having the raised black levels + flat light, again, not a good comparison in my opinion

---

## #479 **Terry Pinfold** (@Terry) · 2026-03-28 19:06

I watch a lot of latest release Korean dramas and often the cinematography is exceptional. I feel a lot of it depends on how the footage is color graded. In the 1970’s most films were relatively disgusting in how they handled night scenes. It seemed that shot in daylight, underexposed and used a tungsten like white balance to add blue to night scenes. Technicolor was one of the greatest color films ever made. The reason, is because it was three strips of black and white film and not color. Then the film was used to produce natural and vibrant color prints for projection. This process is very similar to the RGB sensors now used in digital cameras. We can edit our images with a softness in both color and resolution similar to the film look of yesteryear or we can produce garish vibrant colors and maximize sharpness to produce some modern interpretation of what is good. The skill is in editing to achieve what you desire.

---

## #480 **Yogansh Bhatt** (@Yogansh_Bhatt) · 2026-03-29 16:22

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/5/e5d05672b8f3c7c0068bae869670f60bc2e713ca_2_690x406.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/5/e5d05672b8f3c7c0068bae869670f60bc2e713ca_2_690x406.jpeg)

image1919×1130 434 KB](/uploads/short-url/wN1Hx8Y8L0ycTyH4mrPorAg2ObE.jpeg?dl=1)

Guys we got Positive stocks!

I am loving it : )

Kodachrome 64 here I come!

Ik it is still under development and a lot of stuff like RAW import etc is being setup which is great!

I keep refreshing the commits and we finally got it running on dev and refactor branches.

---

## #481 **** (@Cristian) · 2026-03-29 16:48

Great, I love the Kodachrome 64 look! I actually just bought Fred Herzog’s book, *A Color Legacy*, today and I’m fascinated by his photographs. He used Kodachrome film and the photos has that **oil painting** like quality that we talked about here. You can see some of his work here: [The Estate of Fred Herzog | Artists | Equinox Gallery](https://www.equinoxgallery.com/our-artists/fred-herzog/)

---

## #482 **Benjamin** (@piratenpanda) · 2026-03-29 17:24

kodak and fuji provia velvia give inverted colors for me. what am I doing wrong?

edit: ah i need to tick scan film

---

## #483 **Andrea** (@arctic) · 2026-03-29 23:07

yeah, I had the mind space to re-enter the project in the last couple of weeks

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 and had some fun with refactoring and laying down some ground work to not loose my mind in experimenting with positive film. the positive processing is still kind of hacky and i need to explore more aspects of it, but the profiles shows already some traits of the stocks. saturation might be completely off, and the amount of inhibition couplers should be tuned. they are still not “released” because they are unfinished.

just for fun i added some quality of life improvement to the gui, big work in progress also there. i implemented a few of the ideas that were proposed in the thread, and i have a couple more in the todo list

[[![gui_screenshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/6/f6f0d2c3ab6abdc04e5b9cec7b3aea4c7c4e61f7_2_690x431.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/6/f6f0d2c3ab6abdc04e5b9cec7b3aea4c7c4e61f7_2_690x431.png)

gui_screenshot1920×1200 1.52 MB](/uploads/short-url/zexpZF7tFKNpjWftJqG50rLUkOX.png?dl=1)

i renamed the project to `spektrafilm`, following the suggestion of some members of the forum, that pointed out that the name agx-emulsion is too similar to the agx tonemapper and it creates confusion (amazing work by the way). the new name makes also more sense with the project, i think.

---

## #484 **Tim** (@Soupy) · 2026-03-30 05:36

> **@upperechelonstr8up** (帖子 #467):
> Something i would be very impressed to see from this project in the future is the recreation of old technicolor/eastmancolor/film from the 1990s - backward. I have never seen a film emulation tool (or really modern film in general) emulate that imperfect and almost oil painting like quality, and I have been searching for years on a way to accurately emulate it with very little success since every film emulation plugin/filter is simply concerned with changing the color relationships.

[Technicolor from 1932-1953](https://filmcolors.org/timeline-entry/1301/) (Gone With the Wind, Red Shoes, The Wizard of Oz, etc…) was shot on three separate strips of film. [Technicolor from 1954 on](https://filmcolors.org/timeline-entry/1445/) (Rebel Without a Cause, The Godfather, Vertigo, etc…) was shot on one strip (or three-in-one), though I believe used the same dye transfer process. It is one or both of these that would be the classic technicolor look you are likely referring. (We also have to remember that different cinematography techniques played some part in “the look.”)

I’m not sure whether the linked site has any useful information for these spectral film simulations, but is a goldmine of information about old film stocks.

---

## #485 **Yogansh Bhatt** (@Yogansh_Bhatt) · 2026-03-30 08:41

Great decisions!

The project has always been an exploration quest of sorts to me. Spektrafilm suits it a lot better and we can run it with spektrafilm instead of the script before which is also a small but good change🙂

In my experience with negative stocks, the images from fuji cameras and others already have good levels of contrast but my pixel DNGs usually lack saturation and contrast so playing with it is very rewarding compared to other tools as we have multiple ways to do it with both film and print.

Now with positive stocks print controls are out the window and I don’t have any experience with the development process so I wouldn’t know how that could be handled .

I’ll be running git pull every day.

---

## #486 **** (@Cristian) · 2026-03-30 09:06

Thank you for the updates. Keep up the great work!

---

## #487 **Upperechelonstr8up** (@upperechelonstr8up) · 2026-03-30 13:23

Could you show what the image looks like before the simulation just for comparison?

---

## #488 **jo** (@hanatos) · 2026-03-30 14:01

really cool to see the updates! could you give me some update hints? i noticed you moved dye_density → channel_density, base_density… anything else? maybe different normalisation or scale?

also the positive film seems to be a relatively small change flipping a sign in only a few places, is that right?

[edit] the most important subtle change: empty data points are now `null` instead of `NaN`

---

## #489 **Andrea** (@arctic) · 2026-03-30 21:53

i split the old dye_density in channel_density, base_density, midscale_neutral_density. this is to be able to have cleaner code later for black and white profiles, and naming is more clear.

i haven’t changed much more, i streamlined the profile creation of the negatives and removed unnecessary fittings of the density curves that i had before. so no big changes, mainly refactoring. i want to add black and white level correction, and add the option to save an image “for print”

for now, positive film processing just inverts the sign of the log_exposure correction of inhibition couplers. results are ok, still i haven’t done enough research to be sure this is the best way. i worked mainly on getting the data and exploring the profile creation side.

`null` seems to be the JSON compliant way for missing values.

i changed slightly the profile info, and now i specify type (negative or positive), channel_model (color or bw), and support (film or paper)

---

## #490 **jo** (@hanatos) · 2026-03-31 07:00

thanks! i think i got this working again. for now my stance at positive film is just that it simply skips the printing step and uses the “scan film” code path that i had previously. will do some cleanup/testing and push.

---

## #491 **Andrea** (@arctic) · 2026-03-31 11:27

there is data from color positive print paper, like Kodak Ektachrome Radiance, that could be added to print positive film, I’ll have a look at it.

---

## #492 **Terry Pinfold** (@Terry) · 2026-04-01 01:09

While travelling and trying out a couple of relatively new lenses including a 9mm f2.8 AstrHori lens I thought about this post. I feel some of the look of film stock was not just the film itself but the softer lenses that were around at the time. Now with digital we have very sharp lenses and editing options to sharpen the images even further. The classic USM mask used in digital editing is based on a concept designed in the days of sheet film. I wonder how many if any film photographers here ever made a unsharp mask for printing their film stock. I will be surprised if anyone says they made one to sharpen there film images.

---

## #493 **None** (@Anthonygansauer) · 2026-04-01 11:29

Been reading this thread for some time and have been using the software for some professional. Game changing stuff! I actually shoot mostly on film and ra4 print, Andrea if you need any real world testing let me know! I have acess to endura but mostly print on DPii paper.

[anthonygansauer.com](http://anthonygansauer.com)

---

## #494 **Todd Prior** (@priort) · 2026-04-01 15:02

Thanks for sharing…I love the photo that comes up under the “pride not hate” menu… the expression on your subject and the scene are just amazing…

Welcome to the forum…

---

## #495 **** (@Cristian) · 2026-04-01 15:06

Great photos!

---

## #496 **** (@tankist02) · 2026-04-01 18:37

Support for some positive films was added recently to spektrafilm and ART.

Get latest spektrafilm repo and switch to the dev branch:

```
git clone --recursive https://github.com/andreavolpato/spektrafilm.git
cd spektrafilm
git switch dev
```

Follow installation steps at [https://github.com/andreavolpato/spektrafilm/tree/dev](https://github.com/andreavolpato/spektrafilm/tree/dev)

I used the conda method on my Fedora 43/Gnome OS.

Get latest changes in ART repo and update the command line in ART_agx_film.json for your system. E.g. I have:

```
"command" : "/home/andrew/.conda/envs/spektrafilm/bin/python3.13 spektrafilm_mklut.py --server",
```

Here are a couple of examples:

Provia 100F:

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/3/6364e34ad50dc248987502b41bb87ac7c25451e3_2_690x388.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/3/6364e34ad50dc248987502b41bb87ac7c25451e3_2_690x388.jpeg)

image3840×2160 1.44 MB](/uploads/short-url/ebhq5CVDdrcJ7DTEyfaLPEchPQ7.jpeg?dl=1)

Kodachrome 64:

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/a/2afcc78091385d1267a045e991b5f6dc465c8680_2_690x388.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/a/2afcc78091385d1267a045e991b5f6dc465c8680_2_690x388.jpeg)

image3840×2160 1.35 MB](/uploads/short-url/68hD7gFG6Ihyo8QEeL0K9zaBZtK.jpeg?dl=1)

---

## #497 **Todd Prior** (@priort) · 2026-04-02 04:20

I’m trying this with 1.26.3 on windows…I grabbed the new scripts but I haven’t built ART in a very long time so I was wondering if that might be my issue??..Spektrafilm is installed and runs the gui but either I can’t land on the right command syntax for the Python line in the JSON file or I need an updated build for ART but I can’t get the integration to work in ART.

---

## #499 **None** (@Anthonygansauer) · 2026-04-03 17:41

A cool feature to add would be enlarger diffusion! When you put a diffusion over the enlarger lens you can get the shadows to bloom instead of highlights because everything is inverted, its a very interesting look and tons of folks i know who work in editorial and fashion use it. Will link an example by Jack Orton who uses this method.

[fd360964903bb03732b0058283087f0ecd6c4598-1200x1500|690x862](/uploads/short-url/2VmtAmRwiVB53SRkGzufoW3vYIA.jpeg)

---

## #500 **Andrea** (@arctic) · 2026-04-06 01:29

Gosh, love your photos!

[![:star_struck:](https://discuss.pixls.us/images/emoji/apple/star_struck.png?v=12)](https://discuss.pixls.us/images/emoji/apple/star_struck.png?v=12)

And thanks for the appreciation!

One of the weak point of the full simulation is the calibration of the saturation through the amount of inhibition couplers, they are literally eyeballed (or we let the user adjust as they like). It would be interesting to find a way to anchor sound starting points for saturation levels. I guess fine tuning from experts that work with real ra4 prints should be the best input.

[![:blush:](https://discuss.pixls.us/images/emoji/apple/blush.png?v=12)](https://discuss.pixls.us/images/emoji/apple/blush.png?v=12)

> **@Anthonygansauer** (帖子 #499):
> A cool feature to add would be enlarger diffusion! When you put a diffusion over the enlarger lens you can get the shadows to bloom instead of highlights because everything is inverted, its a very interesting look and tons of folks i know who work in editorial and fashion use it. Will link an example by Jack Orton who uses this method.

I’ll experiment and report back! Looks very cool

---

## #501 **Terry Pinfold** (@Terry) · 2026-04-06 02:29

> **@Anthonygansauer** (帖子 #499):
> you can get the shadows to bloom instead of highlights because everything is inverted

Does DT have a module that will let me invert the image to try and replicate this suggested technique?

---

## #502 **Revanza Pratamasyah** (@Revanza_Pratamasyah) · 2026-04-07 03:32

Hi does anyone know why this happens "An executable named `spektrafilm` is not provided by package `agx-emulsion`.

The following executables are available:

- agx-emulsion.exe"?

---

## #503 **Andrea** (@arctic) · 2026-04-07 05:54

look at the `dev` branch, with the heavy refactoring I was scared to merge to the `main` branch, but maybe I can do it now that I feel a bit more confident that I haven’t messed up too much and tested a bit more the current state

---

## #505 **Rafael** (@dark_photon) · 2026-04-07 11:46

Sorry also posting this here, besides the Spectral film in Art thread!

If anyone wants an easy way to install this (on Linux), I wrote a Nix derivation for it: [GitHub - rafaelcgs10/spektrafilm-art: Spektrafilm and Art bundled together · GitHub](https://github.com/rafaelcgs10/spektrafilm-art)

---

## #506 **WG** (@BPH3647) · 2026-04-07 23:17

I had mentioned the same to someone working on a branch awhile back. I played around with approximating it but its just based off the “scan neg” feature and then roundtrips through photoshop and negative inversion software like NLP. Not worth the effort.

Would love to see a version in spektrafilm! Or even a simple “Print Neg” toggle that bypasses the initial negative conversion.

(Remember your work from a lightlurking post btw. Websites looking better!)

---

## #507 **WG** (@BPH3647) · 2026-04-07 23:40

I had created highlight blooms through the halation feature. Could maybe build that feature off the halation script in the print stage? Pin the CMY to white/neutral and add in a sigma for gaussian blur? Its usually a two step exposure in real life so it might complicate things. Typically something like 15-30% exposure time with anti-newton glass/cigarette wrapper plastic/Black Pro Mist filter in front of the lens and then the remaining image forming time normal.

ps. just tested todays dev branch, please dont get rid of “Print Density Min Factor”!

---

## #508 **** (@mikae1) · 2026-04-08 06:01

How would I run the spektrafilm branch using `uv`? For agx-emulsion I’ve used this script:

```
#!/bin/bash
cd ~/Python/agx-emulsion/
uvx --from git+https://github.com/andreavolpato/agx-emulsion.git agx-emulsion

```

I just tried to create:

```
#!/bin/bash
cd ~/Python/spektrafilm/
uvx --from git+https://github.com/andreavolpato/spektrafilm/tree/dev.git spektrafilm

```

But got:

```
Updating https://github.com/andreavolpato/spektrafilm/tree/dev.git (HEAD)
× Failed to resolve `--with` requirement
 ╰─▶ Git operation failed

```

---

## #509 **Andrea** (@arctic) · 2026-04-08 09:38

> **@Anthonygansauer** (帖子 #499):
> A cool feature to add would be enlarger diffusion!

I tried a quick implementation of the enlarger diffusion. of course it can be tuned to change the shape of the blurring kernel, boosting halo or the bloom tail

no filter

[[![print_scan_no_filter](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/9/f981414380255b845ac1c9fcb7a686098f943e30_2_690x862.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/9/f981414380255b845ac1c9fcb7a686098f943e30_2_690x862.jpeg)

print_scan_no_filter1200×1500 807 KB](/uploads/short-url/zBdOGIKBiVa3kpk1f31u2SdsN32.jpeg?dl=1)

filter strength 1/4

[[![print_scan_0.25](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/c/7ceeac2827e21ae4f1d7b502ca4db748b8437424_2_690x862.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/c/7ceeac2827e21ae4f1d7b502ca4db748b8437424_2_690x862.jpeg)

print_scan_0.251200×1500 723 KB](/uploads/short-url/hPcyHNNq6tQw1ZqX8BKFlDXovMU.jpeg?dl=1)

other filter strengths 1/8, 1/2 and 1

<div class="lightbox-wrapper">[[![print_scan_0.125](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/5/1569b43cd78d255d116dfe1bcddebece7617eafd_2_690x862.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/5/1569b43cd78d255d116dfe1bcddebece7617eafd_2_690x862.jpeg)

print_scan_0.1251200×1500 755 KB](/uploads/short-url/33quNA2mFncaVInGp6OAKnkMk9v.jpeg?dl=1)

[[![print_scan_0.5](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/7/f7735ec53cc97ee002d0c4f447271453b25a93fd_2_690x862.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/7/f7735ec53cc97ee002d0c4f447271453b25a93fd_2_690x862.jpeg)

print_scan_0.51200×1500 683 KB](/uploads/short-url/zj376WboqXkAVaX1UEGY6DXQVCR.jpeg?dl=1)

[[![print_scan_1](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/6/96c8416750d440615f291d9d8d6b00b2c96f9a8a_2_690x862.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/6/96c8416750d440615f291d9d8d6b00b2c96f9a8a_2_690x862.jpeg)

print_scan_11200×1500 636 KB](/uploads/short-url/lvSFhWZYV1JHMo7hG7KtavnRguu.jpeg?dl=1)

</div>

here the diffusion kernel that we might wanna tune

[[![psf_kernel](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/d/5d9cc14b655b456e357509be4cfd1f8341209d4e_2_690x207.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/d/5d9cc14b655b456e357509be4cfd1f8341209d4e_2_690x207.png)

psf_kernel1600×480 101 KB](/uploads/short-url/dm8fyvjBGWBCBpxvhiXFlhbjhue.png?dl=1)

---

## #510 **Andrea** (@arctic) · 2026-04-08 09:41

> **@BPH3647** (帖子 #507):
> ps. just tested todays dev branch, please dont get rid of “Print Density Min Factor”!

my idea was to use the new black and white correction control now in the scanner to act in a similar way. my main gripe about print density min factor is that the base spectral density might not be color neutral, thus it might mess a bit with color balance.

---

## #511 **Andrea** (@arctic) · 2026-04-08 09:43

haven’t tested uv

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 I will have a look to that

---

## #512 **Mica** (@paperdigits) · 2026-04-08 15:52

> **@dark_photon** (帖子 #505):
> If anyone wants an easy way to install this (on Linux), I wrote a Nix derivation for it: GitHub - rafaelcgs10/spektrafilm-art: Spektrafilm and Art bundled together · GitHub

I am the maintainer of ART in nixpkgs and I wouldn’t mind having this in there at all

[![:wink:](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)

---

## #513 **None** (@Anthonygansauer) · 2026-04-08 15:57

And just like that you got it! Awesome man!!!

---

## #514 **** (@Thomsen) · 2026-04-09 11:42

> **@arctic** (帖子 #509):
> I tried a quick implementation of the enlarger diffusion.

Great addition! The initial implementation here seems to have a rather hard falloff, which creates an obvious dark halo and makes the effect seem less integrated into the photo.

Took a while to find actual analogue references, but from what I see the falloff is super soft:

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/e/ce76ebfbcc5f1b9efb653867525b7dfcbf71c5c2_2_517x646.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/e/ce76ebfbcc5f1b9efb653867525b7dfcbf71c5c2_2_517x646.jpeg)

image1080×1350 215 KB](/uploads/short-url/tst99P9PZUoysMcSxpdv3HIJq0y.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/4/84ebaf275c0bcbd5741f348dfc7519ca2cca792b_2_517x623.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/4/84ebaf275c0bcbd5741f348dfc7519ca2cca792b_2_517x623.jpeg)

image1080×1302 260 KB](/uploads/short-url/iXRYAbPr35wyhiFaVI9Dx8EKRDl.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/e/9ecb7f661018988b1a129067e95c435472777584_2_517x373.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/e/9ecb7f661018988b1a129067e95c435472777584_2_517x373.jpeg)

image1080×781 137 KB](/uploads/short-url/mELqMKFOtnzJFggWyY04P836EBK.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/6/c692c09b9eb9ddbebc97507e7e83129a18fbcda0_2_517x376.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/6/c692c09b9eb9ddbebc97507e7e83129a18fbcda0_2_517x376.jpeg)

image1080×786 317 KB](/uploads/short-url/skEXbIx7mKTbDK8bqmrKn840i9G.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/f/cfb029b3749f91aee033ed7a7020b0408c90d5c8_2_517x595.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/f/cfb029b3749f91aee033ed7a7020b0408c90d5c8_2_517x595.jpeg)

image712×820 95.5 KB](/uploads/short-url/tDiglrHkiFP3Vog16sYgLqKoO1y.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/6/3668f44615b5398cceef6cc0bd3c135cf8e93e3a_2_517x641.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/6/3668f44615b5398cceef6cc0bd3c135cf8e93e3a_2_517x641.jpeg)

image750×930 108 KB](/uploads/short-url/7LkE61yKm1aswc25fbLsog1zgJs.jpeg?dl=1)

---

## #515 **Andrea** (@arctic) · 2026-04-09 18:14

Thank you for the reference photos!

---

## #516 **None** (@Anthonygansauer) · 2026-04-10 13:51

Haha 3rd photo down is one of my images!

Something to note is if an exposure is 4 secs long and i want to add diffusion i have to add more density, about 1/3 a stop if i do 50% diffusion.

Base Print Exposure:

4sec f8

Print Exposure with Diffusion:

2.5sec f8 + 2.5secs with diffusion over lens

(and usually i use like a plastic negative sleeve that my negatives come on when i get them developed)

Idk if this helps andre as printing can be deeply personal quess work.

---

## #517 **** (@Thomsen) · 2026-04-10 17:24

Nice shot!

[![:wink:](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)

---

## #518 **Anna** (@betazoid) · 2026-04-11 03:35

[[![IMG_0805](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/3/6348c014decde2a78f018f819fca13abffbf305c_2_690x517.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/3/6348c014decde2a78f018f819fca13abffbf305c_2_690x517.jpeg)

IMG_08053264×2448 1.28 MB](/uploads/short-url/eaj8sn0OwM0KNRzqYbFg6JCAV1q.jpeg?dl=1)

Spektrafilm/ART/vkdt workshop @ Grazer Linuxtage.

[@arctic](/u/arctic) [@agriggio](/u/agriggio) [@grubernd](/u/grubernd) [@hanatos](/u/hanatos)

I hope I/we did not spread too much false info.

Special thanks to [@grubernd](/u/grubernd) for participating in the discussion.

---

## #519 **** (@Thomsen) · 2026-04-11 13:46

When your digital photo sits at the top of the AnalogComunity on Reddit, you know that the emulation is good

[![:wink:](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/a/8a501ec75897eac4e0403827469fb7274e3231ba_2_690x683.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/a/8a501ec75897eac4e0403827469fb7274e3231ba_2_690x683.jpeg)

image987×978 300 KB](/uploads/short-url/jJzxXrnkL6kLUOTRi9odykBrkmu.jpeg?dl=1)

---

## #520 **** (@age) · 2026-04-12 09:33

I was thinking of a way to automatically neutralize the color cast introduced by the film simulation, so not really something in the spirit of this topic but it could be usefull.

The color cast could be removed with rgb curves or with mathematical operator too.

Let’s start with a starting image:

[[![original](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/4/249a2a6eb3f671ffbf03b93e061f18aa53427e1d_2_690x460.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/4/249a2a6eb3f671ffbf03b93e061f18aa53427e1d_2_690x460.jpeg)

original1920×1281 1.32 MB](/uploads/short-url/5dNue5rvltxYuW3g2Cev3ujvV6d.jpeg?dl=1)

The first step is to apply the film simulation on the original image, we could call this image rgb_film_simulation_cc (pratically every pixels in this image are the rgb film simulation results multiplied by a color cast factor):

[[![rgb_film_simulation](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/8/18d09d48cfdd3cd855820c07e8279e348dbb54cc_2_690x460.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/8/18d09d48cfdd3cd855820c07e8279e348dbb54cc_2_690x460.jpeg)

rgb_film_simulation1920×1281 1.44 MB](/uploads/short-url/3xwpDK5LXE3UEOJ4opfwtowsBbK.jpeg?dl=1)

The second step is to apply the film simulation on the grayscale version of the original image, we could call this image gray_film_simulation_cc (pratically every pixels in this image are the grayscale film simulation results multiplied by a color cast factor):

[[![gray_film_simulation](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/b/2b93091d662eb1a206090088438ead1ebfd9febd_2_690x460.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/b/2b93091d662eb1a206090088438ead1ebfd9febd_2_690x460.jpeg)

gray_film_simulation1920×1281 1.18 MB](/uploads/short-url/6dtyjSNWvYJsBLWlvWzbW9RSioB.jpeg?dl=1)

The third step is to remove the saturation from the latest image in step 2:

[[![gray](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/c/2c2deec986e25f28ab87d863243fd64528878c74_2_690x460.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/c/2c2deec986e25f28ab87d863243fd64528878c74_2_690x460.jpeg)

gray1920×1281 1.01 MB](/uploads/short-url/6iPpZmDqoBsScuHUcTygzJ0bLsE.jpeg?dl=1)

Now we just need to apply the follow expression:

Film simulation without color cast = (rgb_film_simulation_cc / gray_film_simulation_cc) * gray

And this is the result:

[[![_MG_3199_04](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/a/7aa10cc8f50338fb48b82cf110a99fe1dfeaa0dc_2_690x460.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/a/7aa10cc8f50338fb48b82cf110a99fe1dfeaa0dc_2_690x460.jpeg)

_MG_3199_041920×1281 1.43 MB](/uploads/short-url/huPiyweR8qMVvX010gaC4LAw2Li.jpeg?dl=1)

How it works?

this part

**(rgb_film_simulation_cc / gray_film_simulation_cc)**

could be written as follow

**(rgb_film_simulation * color_cast) / (gray_film_simulation * color_cast)**

the result is now without the color cast

**rgb_film_simulation / gray_film_simulation**

We just neeed to mutiply this result by the gray_film_simulation image to obtain the rgb_film_simulation without color cast

**rgb_film_simulation / gray_film_simulation * gray_film_simulation**

---

## #521 **Charles** (@Xerxes1138) · 2026-04-12 10:07

Hi,

I’ve installed spektrafilm using pip from the dev branch.

The program run just fine but when I try to save the result I have a “segmentation fault” error then crash.

I’ve tried on small size image and different output type of file without any effect.

Do you know what could be the root cause of this ?

Note that I’m testing this on windows 10 not yet tested on Linux also agx-emulsion worked great.

Thanks a lot for this tool, this is something I was looking for for quite a long time !

---

## #522 **Andrea** (@arctic) · 2026-04-13 14:31

> **@betazoid** (帖子 #518):
> Spektrafilm/ART/vkdt workshop @ Grazer Linuxtage.

wow! that’s kind of amazing! How did it go?

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 would you mind sharing anything about the experience

> **@Thomsen** (帖子 #519):
> When your digital photo sits at the top of the AnalogComunity on Reddit, you know that the emulation is good

that is a great photo, it deserves all the upvotes!

> **@Xerxes1138** (帖子 #521):
> The program run just fine but when I try to save the result I have a “segmentation fault” error then crash.

any additional info to investigate? what python version are you using? have you tried a clean install?

---

## #523 **Andrea** (@arctic) · 2026-04-13 14:46

hej age, thank you for this! it reminds me to get back to a few aspects that i can improve about the profile creation side. i was not fully satisfied by it.

solving and minimizing the color cast of the simulation is a core challenge when creating the film profiles. indeed one of the core principles is to map neutral gray IN to neutral gray OUT (actually i try to correct a neutral gray ramp by minimally modifying the characteristic density curves). little casts are expected because i do not want to mess to much with the original data. I would expect the cast to be overall neutral, i.e. that shadows and highlights should drifts in opposite ways, while midtones should stay relatively neutral.

one note, if the virtual enlarger is applying a color correction with the yellow and magenta filters, it is expected that a neutral gray input will provide an output with a color cast. if a strong color cast is there for neutral gray it might be unwanted (bug/mistake), or a challenging film stock. do you consistently notice unwanted casts? could you fix them just by optimizing the enlarger filters? in that case the problem would be in the precomputed neutral enlarger filters.

---

## #524 **Gustavo Adolfo** (@gadolf) · 2026-04-13 16:39

Hi!

I can’t open navari:

```
gustavo@CAURJ004:~/.local/bin$ /home/gustavo/.local/bin/uvx --from git+https://github.com/andreavolpato/spektrafilm.git spektrafilm
An executable named `spektrafilm` is not provided by package `agx-emulsion`.
The following executables are available:
- agx-emulsion

```

This is Debian 12

NOTE: I had previously installed the version from the main branch successfully. Navari opened the interface, but I couldn’t open an .exr file, so I decided to try the dev branch

---

## #525 **Andrea** (@arctic) · 2026-04-13 18:22

try with this command:

```
uvx --from git+https://github.com/andreavolpato/spektrafilm.git@dev spektrafilm

```

i updated the readme, too.

> **@mikae1** (帖子 #508):
> How would I run the spektrafilm branch using uv? For agx-emulsion I’ve used this script:

should answer the question you also had, [@mikae1](/u/mikae1)

---

## #526 **Charles** (@Xerxes1138) · 2026-04-13 18:45

I tried a clean install and I have python 3.13 installed. Other than the “segmentation fault” I don’t have much more info.

Maybe I can enable some debug somehow when the program is running, but I don’t know how.

---

## #527 **Charles** (@Xerxes1138) · 2026-04-13 18:50

This solved my problem too!

---

## #528 **Vicer Fx** (@Vicer_Fx) · 2026-04-13 20:18

I think your examples have more to do with the cinematography style than the film stock used. Lighting is really different from modern movies

---

## #529 **** (@mikae1) · 2026-04-14 04:46

> **@arctic** (帖子 #525):
> uvx --from git+https://github.com/andreavolpato/spektrafilm.git@dev spektrafilm

Cool, works well! Thanks! Kind of a quantum leap in terms of UX compared to the agx-emulsion days.

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

---

## #530 **Anna** (@betazoid) · 2026-04-14 14:25

> **@arctic** (帖子 #522):
> wow! that’s kind of amazing! How did it go? would you mind sharing anything about the experience

I had the impression that it was a big success. There were approximately 30 participants which is great because at my previous photo editing Workshops at the Libre Graphics Meeting there were 2-5 participants. As far as my „pediagocial method“ is concerned, it was a dream, the participants actually participated and it was not just like s talk, we actually had a fruitful dialogue, especially thanks to [@grubernd](/u/grubernd) who is a professional photographer. I think this was my most successful And „pleasant“ workshop at a conference so far. Of course, most listeners were just Linux nerds and had not much experience in photo editing, but they quickly understood what was important and I think I could convince some of them that spektrafilm is a wonderful piece of software. Of course I dont know yet what the actual feedback is. I didnt know many people at the conference and therefore didnt talk with many people. The whole conference consisted of just two days, the workshops were on Friday and the talks on Saturday. Well and even though I am not exactly an award winning actress I was actually able to talk, thanks to the fact that is was more like a dialogue. Just one thing, which was my fault: we only had a projector and not a big screen (i should have asked the organizers for a screen), but it was good enough to show the difference between kodak portra and kodak gold.

---

## #531 **Andrea** (@arctic) · 2026-04-15 18:07

it sounds it was a success! i’m very glad! thank you for sharing this insight and congratulations on 30 participants and the nice idea

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

---

## #532 **Upperechelonstr8up** (@upperechelonstr8up) · 2026-04-18 05:01

Nah, I’m referring to the way the different colors blend into each other in a soft and imperfect way appose to sterile and clean. Upon further research on this topic i think the answer might actually have something to do with film stock. A clear example of this (again happening in the late 2000s) can be seen in the change between breaking bad season 1 versus season 2 onward. I’ve heard that the reason for this had something to do with the crew switching from Fujifilm to Kodak stock (as well as a different cinematographer). The specifics of whatever stock was used I don’t know, but if i had to guess the Kodak stock used was probably some new cleaner updated variation that probably became widespread throughout the industry.

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/9/298f491d205f8947640111f7c9b4c502b8af3a49_2_690x339.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/9/298f491d205f8947640111f7c9b4c502b8af3a49_2_690x339.jpeg)

image1920×946 496 KB](/uploads/short-url/5VEyZ3PCfWNivrEJ3nHIe3jcrVv.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/c/fc5216bd3cdfa8c1c35b763618c89fc8ffa154f4_2_690x339.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/c/fc5216bd3cdfa8c1c35b763618c89fc8ffa154f4_2_690x339.jpeg)

image1920×946 275 KB](/uploads/short-url/A08cdsskZVIoWhoj8R95Uyxqscs.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/5/6513bd054f3c51fd1827b27eb54bf532ddd591a8_2_690x339.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/5/6513bd054f3c51fd1827b27eb54bf532ddd591a8_2_690x339.jpeg)

image1920×946 197 KB](/uploads/short-url/eqavQTKb1qpCfZ3LksVD2eq4gvC.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/d/6d7f9beea76f19681949be0a2d475f3eda98655f_2_690x339.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/d/6d7f9beea76f19681949be0a2d475f3eda98655f_2_690x339.jpeg)

image1920×946 377 KB](/uploads/short-url/fCFrCDUTWHNwv0hXHXx9Wxs7QBN.jpeg?dl=1)

Season 1 above

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/7/a7bf16aa1d1aa7433464ba4bb5136d3caba20e3b_2_690x339.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/7/a7bf16aa1d1aa7433464ba4bb5136d3caba20e3b_2_690x339.jpeg)

image1920×946 361 KB](/uploads/short-url/nVX8R9mGHDiuiLWSBZqspdAqzaP.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/9/b917b755ae9962de02db7f07ca5f2c5507667aa8_2_690x339.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/9/b917b755ae9962de02db7f07ca5f2c5507667aa8_2_690x339.jpeg)

image1920×946 295 KB](/uploads/short-url/qpp8UcqOlflLmu17CL9MLq7XVvG.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/2/e2cad287e80ace6129a1988a207acab60a56a28e_2_690x339.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/2/e2cad287e80ace6129a1988a207acab60a56a28e_2_690x339.jpeg)

image1920×946 325 KB](/uploads/short-url/wmis6pj2XaNf3oOmvAqT6vzR4bI.jpeg?dl=1)

Season 3 above

I don’t believe the lighting to be that different between these two sets of images, i tried to find similar looking shots. The stock is much more cleaner and in my opinion, the season 3 images could have very well be shot on digital and there would be very little difference.

---

## #533 **** (@Thomsen) · 2026-04-18 08:14

A shame they changed cinematographer as well, that makes it difficult to compare. I think I understand the feeling of old film that you’re trying to convey, but I am uncertain whether or not it is different stocks, the development process, digitalization processes (more sharpening) or just different cinematography styles.

I would agrue that the lighting is vastly different between these two sets of frames (more so than the quality of the film stock):

Harsh sunlight with crushed shadows:

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/6/e683387af989a82f70545a91056ba9157410e953_2_345x169.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/6/e683387af989a82f70545a91056ba9157410e953_2_345x169.jpeg)

image1035×508 162 KB](/uploads/short-url/wTcXl5s6ffTDvBKZkdNR7MygPDR.jpeg?dl=1)

Super soft key light (Kinoflo or softbox):

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/e/5ecedce9fa8b3226aec745cb328cddbc709d5de5_2_345x169.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/e/5ecedce9fa8b3226aec745cb328cddbc709d5de5_2_345x169.jpeg)

image1035×508 90.3 KB](/uploads/short-url/dwI5d2GOuR50H53CFKutr0yKGX3.jpeg?dl=1)

Backlit with a subtle warm fill to lift her face

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/5/15efabcfa60457c6788ccb1f2e8c08e2d3116172_2_345x169.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/5/15efabcfa60457c6788ccb1f2e8c08e2d3116172_2_345x169.jpeg)

image1035×508 91.9 KB](/uploads/short-url/383weA8D1ZToInESj83fFGVT5cu.jpeg?dl=1)

Low sun, probably diffused (Much softer and warmer light than the exterior shot from season one)

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/5/85ed609a2293bc3e93e908003a9b5cd44531093a_2_345x169.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/5/85ed609a2293bc3e93e908003a9b5cd44531093a_2_345x169.jpeg)

image1035×508 94.6 KB](/uploads/short-url/j6M55YIADzGNcqwBibx6mlcEZZw.jpeg?dl=1)

---

## #534 **WG** (@BPH3647) · 2026-04-18 14:32

Understandable! I use (used) it in the opposite way. Its a nice way to knock down the whites when everything is looking good but the high end needs an extra slight nudge down. I used it in conjunction with preflash but extra flash alters the image significantly more and differently than the min function- to my eyes at least.

The base tint might actually be a feature more than you expect as RA-4 paper does have a natural base tint that feeds into the look. Endura of the recent years actually had quite a warm base (some batches even had a green tint).

This is a comparison I made while trying to sort out discrepancies between Endura rolls with a supplier.

[[![Kodak-Kodak-Compare-02](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/9/8934277a47b61f3700807a9faf419816d1d73465_2_345x455.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/9/8934277a47b61f3700807a9faf419816d1d73465_2_345x455.jpeg)

Kodak-Kodak-Compare-021364×1800 1.22 MB](/uploads/short-url/jzL9voTaZ7wT7CLLBx2PUfIcoJv.jpeg?dl=1)

I’ve certainly put the software through its paces so some features might be hard to let go of, haha. Wonderful work on the newest versions functionality. The ability to save settings has saved my desktop from an absolute pigpile of screenshots

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

---

## #535 **** (@mikae1) · 2026-04-18 22:02

> **@BPH3647** (帖子 #534):
> The ability to save settings has saved my desktop from an absolute pigpile of screenshots

Haha, relatable! Did not know about the settings saving, thanks!

---

## #536 **Andrea** (@arctic) · 2026-04-20 17:28

that is interesting to know, thank you for the comparison!

we could add a tunable custom base, so we can creatively tune the minimum density and the color tint, knowing that it will mess a little with the pre-optimized neutral gray calibration.

i’ll give it a spin.

---

## #537 **None** (@Anthonygansauer) · 2026-04-20 19:17

How does one go about using the slide films without print emulations?

---

## #538 **Andrea** (@arctic) · 2026-04-20 19:51

right now in main and dev branches, slide film does not go through the printing by default and it is scanned directly, but you can always click/declick “scan film” to toggle that

---

## #539 **Vicer Fx** (@Vicer_Fx) · 2026-04-21 21:21

I’ve been messing with the tool these days and I’m in love with it. Do you plan on adding older film stocks? I think it would be nice to see some kodak 5247/5248 or exr

---

## #540 **Andrea** (@arctic) · 2026-04-22 00:28

if there are stocks with a special look or worthy to add it is a very good idea!

happy to learn what is loved, or historically relevant

i found this for the 5247 [https://125px.com/docs/motionpicture/kodak/ti0835.pdf](https://125px.com/docs/motionpicture/kodak/ti0835.pdf)

and this for the 5248 exr [https://125px.com/docs/motionpicture/kodak/5248.pdf](https://125px.com/docs/motionpicture/kodak/5248.pdf)

anything else from this pool of datasheets that would be cool to have?

[https://125px.com/docs/motionpicture/kodak/](https://125px.com/docs/motionpicture/kodak/)

and

> **@upperechelonstr8up** (帖子 #532):
> Nah, I’m referring to the way the different colors blend into each other in a soft and imperfect way appose to sterile and clean. Upon further research on this topic i think the answer might actually have something to do with film stock.

i guess having some older film stocks profiles might help getting an older look, so having them would definitely not hurt

[![:wink:](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)

> **@Thomsen** (帖子 #533):
> I would agrue that the lighting is vastly different between these two sets of frames (more so than the quality of the film stock)

even if i agree with [@Thomsen](/u/thomsen), that cinematography, lighting, development processes, and analog post-production can have a very big impact in the final look. the film stock is one of the many ingredients

---

## #541 **Tim** (@Soupy) · 2026-04-22 02:03

> **@arctic** (帖子 #540):
> if there are stocks with a special look or worthy to add it is a very good idea!
happy to learn what is loved, or historically relevant

Autochrome!

---

## #542 **** (@Thomsen) · 2026-04-22 07:32

> **@arctic** (帖子 #540):
> anything else from this pool of datasheets that would be cool to have?
Index of /docs/motionpicture/kodak

If you eventually travel into B&W territory, double-X and tri-X are both killer stocks!

---

## #543 **Vicer Fx** (@Vicer_Fx) · 2026-04-22 19:33

[https://125px.com/docs/motionpicture/kodak/lab/h15386.pdf](https://125px.com/docs/motionpicture/kodak/lab/h15386.pdf) this is a print from the 90s, used in forrest gump

[https://filmcolors.org/wp-content/uploads/2015/02/Carl_Erwin_etal_Print5384_1982.pdf](https://filmcolors.org/wp-content/uploads/2015/02/Carl_Erwin_etal_Print5384_1982.pdf) and this one was used to be together with 5247, used in star wars, indianna jones, etc.

I also think eterna could be a nice adittion (this repository has another datasheets too) [spectral_film_lut/datasheets/Fuji_3513DI.pdf at main · JanLohse/spectral_film_lut · GitHub](https://github.com/JanLohse/spectral_film_lut/blob/main/datasheets/Fuji_3513DI.pdf)

---

## #545 **None** (@Anthonygansauer) · 2026-04-22 23:00

[[![Datasheet](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/d/4dbfa176b22811ece7aa0e03d27450a526942c44_2_690x552.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/d/4dbfa176b22811ece7aa0e03d27450a526942c44_2_690x552.jpeg)

Datasheet5906×4725 3.79 MB](/uploads/short-url/b5NkAL07EhqVNiJNIxuJMr060yo.jpeg?dl=1)

didnt realize tiff dont open in the chat, heres a jpeg

---

## #546 **None** (@Anthonygansauer) · 2026-04-22 23:14

after messing with print exposure the colors are reallyyyyyy close, just color density is a bit off, just need to darken reds and blues a bit (or could because this isnt a accurate comparison)

---

## #547 **Andrea** (@arctic) · 2026-04-23 00:01

thank you for the comparison [@Anthonygansauer](/u/anthonygansauer)!

would you mind sharing also the closer match by tuning the printing parameters?

**sidenote**: could you edit your previous post with the 120MB png, and replacing with a smaller file, keeping stuff limited to a few MB is a great favor for the maintainers of the forum that are managing the storage

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

I am very glad about your comment on reds and blues. you are striking a very interesting point of the simulation that is not rock solid at this point, and that i wanna work more in the near future.

you could give it a shot and play a little with it, you can use the IR and UV filters in the `advanced`>>`spectral upsampling` widget. right now the values were just eyeballed but in the todo there is “finding a way to better match them with real images”. so this insight is very precious.

essentially they are virtual filter to limit the blue and red region of the spectra where the sensitivities of the film go past the standard observer sensitivities (human vision). they are very arbitrary right now, but necessary to tame the spectral upsampling algorithm that act uncontrolled past the human vision region.

[[![band_pass_and_portra_sensitivities](https://d2x313g9lpht1q.cloudfront.net/original/3X/3/8/3826a963bcb5dad6401167a08be5fdf1cd032cae.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/3/8/3826a963bcb5dad6401167a08be5fdf1cd032cae.png)

band_pass_and_portra_sensitivities640×494 59.1 KB](/uploads/short-url/80JznpYS67JBezJ8IupzSeasjP8.png?dl=1)

above is a plot of the current default filters, you can see a clear cut on the blue, while we are a bit more permissive on the red side.

the tedious part is that while tuning them you are also messing with the color balance and you always have to reoptimize the printing filters

here is an example:

[[![645nm -10Y -10M](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/b/cb72f594ac06ff2d262ca0b382d7930be942c42b.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/b/cb72f594ac06ff2d262ca0b382d7930be942c42b.jpeg)

645nm -10Y -10M640×426 160 KB](/uploads/short-url/t1NdZsiSRjmATL342aIQeS3QG0P.jpeg?dl=1)

[[![default filters](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/3/5391696b174d95949d8aa44227a91c0c155312be.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/3/5391696b174d95949d8aa44227a91c0c155312be.jpeg)

default filters640×426 164 KB](/uploads/short-url/bVhaKrdxGA1zCqXCpkQfaeSSfPU.jpeg?dl=1)

(left) 410nm, 8nm / 645nm, 15nm and -10Y/-10M (right) default, ie 410nm, 8nm / 675nm, 15nm. All other parameter are exactly the same and default.

each filter has two paramters: (i) center of the transition, (ii) width of the transition, both in nanometers.

the blue side will work similarly with the UV filter.

having good quality digital/analog pairs is indeed a way to guess this. in a perfect world one would optimize a set of filters for every stock, but we need to start somewhere.

[![:grin:](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)

---

## #548 **** (@mikae1) · 2026-04-23 14:42

Been syphoning up some data sheets from [kodakprofessional.com](http://kodakprofessional.com) and [fujifilm.com](http://fujifilm.com) and archiving them using Wayback Machine. They’re probably available from that other open directory that has been floating around here, but here are (hopefully) the latest versions available from the source of truth.

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

[filetype:pdf “spectral” site:kodakprofessional.com](https://www.google.com/search?q=filetype%3Apdf%20%22spectral%22%20site%3Akodakprofessional.com) search:

- [KODAK PROFESSIONAL PORTRA 160 Film](https://web.archive.org/web/20260423141218/https://kodakprofessional.com/sites/default/files/2025-07/e4051.pdf)
- [KODAK PROFESSIONAL PORTRA 400 Film](https://web.archive.org/web/20260423141234/https://kodakprofessional.com/sites/default/files/2025-07/e4050.pdf)
- [KODAK PROFESSIONAL PORTRA 800 Film](https://web.archive.org/web/20260423080046/https://kodakprofessional.com/sites/default/files/2025-07/e4040.pdf)
- KODAK GOLD 200 Film[[1](https://web.archive.org/web/20260423141334/https://kodakprofessional.com/sites/default/files/wysiwyg/E7022-1.pdf)][[2](https://web.archive.org/web/20260423141645/https://kodakprofessional.com/sites/default/files/wysiwyg/pro/resources/E7022%20Gold%20tech%20sheet.pdf)]
- [KODAK PROFESSIONAL EKTAR 100 Film](https://web.archive.org/web/20260423141327/https://www.kodakprofessional.com/sites/default/files/2025-07/e4046.pdf)
- [KODAK ULTRA MAX 400 Film](https://web.archive.org/web/20260423141703/https://www.kodakprofessional.com/sites/default/files/wysiwyg/KodakUltraMax400TechSheet-1.pdf)
- [KODAK PROFESSIONAL T-MAX 100 Film](https://web.archive.org/web/20260423141745/https://www.kodakprofessional.com/sites/default/files/wysiwyg/pro/resources/f4016_TMax_100.pdf)
- [KODAK PROFESSIONAL TRI-X 320 and 400 Films](https://web.archive.org/web/20260423141727/https://kodakprofessional.com/sites/default/files/wysiwyg/film/f4017_trix_320400.pdf)

[filetype:pdf “film” site:fujifilm.com “spectral”](https://www.google.com/search?q=filetype%3Apdf%20site%3Afujifilm.com%20%22spectral%22) search:

- [FUJICOLOR C200](https://web.archive.org/web/20260423143037/https://asset.fujifilm.com/master/emea/files/2020-10/98c3d5087c253f51c132a5d46059f131/films_c200_datasheet_01.pdf)
- [FUJICOLOR PRO 400H PROFESSIONAL](https://web.archive.org/save/https://asset.fujifilm.com/master/emea/files/2020-10/a6cb96275e4957ddc7b3ca932b7755e5/films_pro-400h_datasheet_01.pdf)
- [FUJICOLOR SUPERIA X-TRA 400 [CH]](https://web.archive.org/web/20260423143044/https://asset.fujifilm.com/master/emea/files/2020-10/9a958fdcc6bd1442a06f71e134b811f6/films_superia-xtra400_datasheet_01.pdf)
- [FUJICHROME PROVIA 100F Professional [RDPIII]](https://web.archive.org/web/20260423143257/https://asset.fujifilm.com/master/emea/files/2020-10/2c27854d5609945fbe7e48afc61f815d/films_provia-100f_datasheet_01.pdf)
- [FUJICHROME Velvia 100 Professional [RVP100]](https://web.archive.org/web/20260423143110/https://asset.fujifilm.com/master/emea/files/2020-10/2f3c7f90a0b0c6e605e84f98b7d489c2/films_velvia-100_datasheet_01.pdf)
- [FUJICHROME Velvia RVP for Professionals](https://web.archive.org/web/20260423143121/https://asset.fujifilm.com/www/us/files/2020-03/64873257f4644939d7bd75d95600a561/AF3-960E.pdf)
- [FUJICOLOR Nexia Zoom Master 800](https://web.archive.org/web/20260423143132/https://asset.fujifilm.com/www/jp/files/2019-09/47ce4268600cbc8f9d4d6cd15edb8e25/rd_report_ff_rd046_002.pdf)
- [Fujichrome PROVIA 400X](https://web.archive.org/web/20260423143344/https://asset.fujifilm.com/www/jp/files/2019-10/9de33adc9ad4a37e6be7947a9b289d55/rd_report_ff_rd052_002.pdf)
- [Fujicolor Super400/Nexia H400](https://web.archive.org/web/20260423143440/https://asset.fujifilm.com/www/jp/files/2019-09/016eb45e2174d5a03a79717257aa0118/rd_report_ff_rd044_002.pdf)
- [ETERNA-RDS 35mm Type 4791 (PET)](https://web.archive.org/web/20260423143501/https://asset.fujifilm.com/www/us/files/2023-10/8cb7293542ed10e48caad7eaacc5365a/eterna_rds.pdf)
- [NEOPAN 100 ACROS](https://web.archive.org/web/20260423143606/https://asset.fujifilm.com/www/us/files/2020-04/299395cd078366c7a2956af612ca9fdb/NeopanAcros100.pdf)
- [NEOPAN 100 ACROSII (135)](https://web.archive.org/web/20260423143628/https://asset.fujifilm.com/www/ca/files/2020-07/fb477bd9803b3c27ab592edcf9f3567c/AF3-0258E_PIB-NEOPAN-100-ACROSII-135-3_data-sheet.pdf)
- [NEOPAN 100 ACROSII (120)](https://web.archive.org/web/20260423143613/https://asset.fujifilm.com/www/au/files/2020-10/fe47fac3c002c381e48434f565fe44af/NEOPAN-100-ACROSII.pdf)
- [NEOPAN 1600 SUPER PRESTO](https://web.archive.org/web/20260423143627/https://asset.fujifilm.com/www/jp/files/2019-12/a80cda9888a206303c836f7ffd99709b/datasheet_neopan1600superpresto_en_01.pdf)
- [NEOPAN SS (135)](https://web.archive.org/web/20260423143802/https://asset.fujifilm.com/www/jp/files/2019-12/5cff4aeedafee45ce703f57552de76e6/datasheet_neopanss_en_01.pdf)
- [Development of New Color Reversal Film FUJICHROME “Velvia 100F and 100”, and “ASTIA 100F”](https://web.archive.org/web/20260423143805/https://asset.fujifilm.com/www/jp/files/2019-10/d2a435c2e3c6481447ecdbc0c29d75f0/rd_report_ff_rd049_003.pdf)

---

## #549 **Andrea** (@arctic) · 2026-04-23 14:58

thanks!!! i will hoard this files for my personal collection, and soon decide on what to include in the next campaign of digitazion. recent datasheet that are in vectorial form are easier to digitize because can be isolated from labels and grids with ease.

> **@mikae1** (帖子 #548):
> Development of New Color Reversal Film FUJICHROME “Velvia 100F and 100”, and “ASTIA 100F”

i am absolutely in love with this file

[![:heart_eyes:](https://discuss.pixls.us/images/emoji/apple/heart_eyes.png?v=12)](https://discuss.pixls.us/images/emoji/apple/heart_eyes.png?v=12)

 i do not know japanese but it looks so information dense compared to typical datasheets, and it hints to so much depth into the details of the advanced inner workings of modern slide film, with what appears as masking couplers (that i do not simulate in slide for now), color matching functions, comparisons of stocks. it is just beautiful.

by the way. fun fact. digitizing datasheets is a very manual process and after a few days of trying to fix strange behaviors of kodak portra and supra papers, i found that their sensitivities had the wavelength axis stretched by 50 nm too much (that it is kinda huge). it made me crazy trying to understand the issues with green and those papers with the updated way of processing the datasheets. at last i fixed it one week ago, now is fine also in `main`. but the madness of the rabbit-hole-problem-hunting made me discover additional nice details.

---

## #550 **** (@mikae1) · 2026-04-23 15:11

NP!

[![:heart:](https://discuss.pixls.us/images/emoji/apple/heart.png?v=12)](https://discuss.pixls.us/images/emoji/apple/heart.png?v=12)

> **@arctic** (帖子 #549):
> i am absolutely in love with this file i do not know japanese but it looks so information dense compared to typical datasheets, and it hints to so much depth into the details of the advanced inner workings of modern slide film, with what appears as masking couplers (that i do not simulate in slide for now), color matching functions, comparisons of stocks. it is just beautiful.

Oh, I found more of those I think, but thought they might not be interesting

[![:smiley:](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)

Might have to look again then!

---

## #551 **jo** (@hanatos) · 2026-04-23 15:26

> **@arctic** (帖子 #549):
> at last i fixed it one week ago, now is fine also in main.

ouch! i need to update my data!

---

## #552 **Andrea** (@arctic) · 2026-04-23 15:39

better profiles are also coming soon, mainly I neutralized better slide film so white balance is more consistent across stocks with the reference illuminant of choice. this possibly is removing some of the specific characteristics but it makes the profiles more usable and predictable (and removes possible neutrality issues of the data).

plus a more sophisticated non linear way of unmixing status densities (that is important for the high density part of the curves). I have some more testing to do but I will update on how it goes, and if they will show any clear difference in the final visual results.

---

## #553 **None** (@Anthonygansauer) · 2026-04-23 19:33

[[![example](https://d2x313g9lpht1q.cloudfront.net/original/3X/e/c/ec362ede6d2181bcbb462d62605d0ab56c0cc2fc.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/e/c/ec362ede6d2181bcbb462d62605d0ab56c0cc2fc.jpeg)

example268×224 50.7 KB](/uploads/short-url/xHCLITdqKX7V3RkQ1XDPjtfEZYM.jpeg?dl=1)

matched density and exposure, no color edits at all. its almost a perfect match. this is honestly insane

---

## #554 **None** (@Anthonygansauer) · 2026-04-23 19:41

going to try a real test one of these days with my nikon f4 as i have two 24mm lens i can adapt for my lumix & nikon. this is seriously some ground breaking stuff man.

i am definitely super excited for any kodachrome emulations as I wasnt even born when it was primarily used but all the work i admire from the natgeo, street, and photo journalist stuff-- I am anxious awaiting it to be developed further!

---

## #555 **** (@mikae1) · 2026-04-23 19:43

> **@mikae1** (帖子 #550):
> Might have to look again then!

Here are a few possibly interesting ones:

- [Fujifilm Professional Data Guide](https://web.archive.org/web/20260423192431/https://asset.fujifilm.com/www/ca/files/2020-03/d52487c5c6f84e7f935c299491c5c1ff/ProfessionalFilmDataGuide.pdf)
- [Development of Motion-picture Recording Film ETERNA-RDI](https://web.archive.org/web/20260423193633/https://asset.fujifilm.com/www/jp/files/2019-12/086cdc8636ea5ed63f24d1d3fc3df626/ff_rd053_001_en.pdf)
- [Development of Fujichrome ASTIA100](https://web.archive.org/web/20260423194023/https://asset.fujifilm.com/www/jp/files/2019-10/e4c329ecef963aa7eb37aabe23eb0364/rd_report_ff_rd043_001.pdf)

> **@arctic** (帖子 #549):
> by the way. fun fact. digitizing datasheets is a very manual process and after a few days of trying to fix strange behaviors of kodak portra and supra papers, i found that their sensitivities had the wavelength axis stretched by 50 nm too much (that it is kinda huge). it made me crazy trying to understand the issues with green and those papers with the updated way of processing the datasheets. at last i fixed it one week ago, now is fine also in main. but the madness of the rabbit-hole-problem-hunting made me discover additional nice details.

That’s pretty wild, nice find! Love hearing these development stories!

[![:smiley:](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)

---

## #556 **jo** (@hanatos) · 2026-04-24 07:10

<pre data-code-wrap="diff"><code class="lang-diff"> [
 null,
- 1.012518727450156,
- 1.7554564241334116
+ -1.2157949931727523,
+ -0.4946460830254054
 ],
</code></pre>

oh, did everything become a lot darker? this is from the `log_sensitivity` table in the portra 160 data. what else should i be re-normalising in different ways now? without further changes i’ll render everything black. also need to re-calibrate the white balancing of course.

[edit: for now i mutiplied the film exposure light `*1000.0` and it’s kinda back to normal. updated the vkdt data to upstream]

---

## #557 **Andrea** (@arctic) · 2026-04-24 12:31

in negative and positive film i normalize with the spectrum upsampled for midgray = [0.184, 0.184, 0.184] (that is essentially the reference illuminant bandpass-filtered, i consider the bandpass as part of the spectral upsampling). so when inputting midgray as input i get zero log exposure for the three channels. the spectral upsampling spectra are computed with code very similar to the one you shared to me last year, i hope i didn’t add other weird normalizations there.

for print media i normalize sensitivities with the printing illuminant attenuated by the mid density published for the reference target film (portra 400 for kodak, vision3 250d for cine kodak, pro 400h for fuji paper) and enlarger filters set to Y50M50(C0) CC units (100 kodak CC units is 1 OD, and for Durst enlargers 100 steps is in the ball park of 50CC). in this way i get neutral filters fitted in a reasonable range without pushing the density of the enlarger filters too much. i changed also the scale of the filters, now linear in density, because they are like this in real enlargers, and i avoid to get filter values crashing to 1.

---

## #558 **jo** (@hanatos) · 2026-04-27 09:22

> **@arctic** (帖子 #557):
> in negative and positive film i normalize with the spectrum upsampled for midgray = [0.184, 0.184, 0.184] (that is essentially the reference illuminant bandpass-filtered, i consider the bandpass as part of the spectral upsampling).

ah, nice. that sounds good. i need to think about whether colours on the purple line (spectra with *dips* not *lobes*) would fall off to zero at all or just be clipped at the maximum evaluation range. does the middle grey spectrum fall off to zero? or is this about frequency domain over lambda more than uv and near-ir?

> **@arctic** (帖子 #557):
> i changed also the scale of the filters, now linear in density, because they are like this in real enlargers, and i avoid to get filter values crashing to

that sounds really useful. it’s a ui change / breaking history (but i keep doing that in this filmsim module…), but also something that would potentially help the white balance optimiser to be more stable. i might experiment with this too, probably a good idea to stick as closely as possible to your implementation anyways. even if these particular changes seem to be more constant normalisation offsets or paramater sensitivity changes that could likely be compensated by user settings and wouldn’t in general lead to a different output/expressivity.

---

## #559 **Andrea** (@arctic) · 2026-04-27 19:12

> **@hanatos** (帖子 #558):
> does the middle grey spectrum fall off to zero? or is this about frequency domain over lambda more than uv and near-ir?

i am not sure about the extreme purple line, i am pretty sure it will suffer, but during the weekend i got some results from a sidequest: trying to optimize the bandpass filters for every stock. the results might give some insight on these questions (and there might be pitfalls). any feedback is very welcome of course!

i wrote a little optimizer that fit a 6 parameters band pass model to minimize the delta exposure of a measured dataset of real spectra vs the upsampled versions (the loss function is the sum of the difference of log exposure per channel). clearly the problem is imperfect by definition and there is no perfect solution, but it seems we can do a decent job for many film stocks and a good job for some of them.

essentially we are comparing integral(real_spectra x sensitivities) and integral(upsampled_spectra x sensitivities x bandpass). we can view it as reducing the near-uv-ir sensitivities or reducing the near-uv-ir upsampled spectra energy. i monitor the result using

\rho_i
= \max_{c \in \{R,G,B\}}
\frac{\left|H^{\mathrm{true}}_{i,c} - H^{\mathrm{hat}}_{i,c}\right|}{H^{\mathrm{true}}_{i,c}}.

where H^true are the exposure of the real measured spectra and H^hat the exposure of upsampled bandpassed spectra. as a reference value we can use 1/20 of a stop as the minimum delta exposure that will produce a percievable difference that correspont to about 0.035 in the rho_i scale (rho_i < tau_phot = 0.035 should be excelent). also we can define the hard spectra as being rho_i > 8*tau_phot for the uncorrected case.

i am trying to inject knowledge on the behavior of typical spectra in the edge of the visible spectrum to tame the upsampler. the dataset is made by: (i) the otsu2018 raw spectra dataset that they used in their upsampling method, (ii) nist skin dataset and (iii) forest colors to anchor the two most important memory colors, and (iv) a Munsell dataset (50/20/20/10 share in the loss).

[[![f02_xy-coverage__shared_corpus](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/1/21b64692e8bdc46548f0f9ef144a1c46b3c80ff1_2_690x509.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/1/21b64692e8bdc46548f0f9ef144a1c46b3c80ff1_2_690x509.png)

f02_xy-coverage__shared_corpus1992×1472 337 KB](/uploads/short-url/4OehnJ98LqBWcuZ3bTSs8dMvWvv.png?dl=1)

[[![f01_envelope__shared_corpus](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/7/c7c748f5b3214f63587a309e71d215b49d8b08ce_2_690x305.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/7/c7c748f5b3214f63587a309e71d215b49d8b08ce_2_690x305.png)

f01_envelope__shared_corpus2194×972 129 KB](/uploads/short-url/svjYVJoXUHcF18rgmHWkZ67CejY.png?dl=1)

you can see that skin and vegetation reflectance have strong energy in the near-ir, and munsell has some spectra with energy below 400 nm.

if we now optimize for **kodak_portra_400** and compute the rho_i for all the spectra we get:

[[![f04_sens-window__kodak_portra_400_hanatos2025_log_mse_perchan6_D55_3cab88db60a471c3](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/6/76e3c9c041ad83c4616e2cced766129b2a0bb886_2_690x727.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/6/76e3c9c041ad83c4616e2cced766129b2a0bb886_2_690x727.png)

f04_sens-window__kodak_portra_400_hanatos2025_log_mse_perchan6_D55_3cab88db60a471c31925×2029 326 KB](/uploads/short-url/gXKngrjU67V9k8Kb0aaowcOcKr4.png?dl=1)

[[![f07_rho-ecdf__kodak_portra_400_hanatos2025_log_mse_perchan6_D55_3cab88db60a471c3](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/6/067563145ff0a37634b3d281f62d273f2964a43c_2_690x665.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/6/067563145ff0a37634b3d281f62d273f2964a43c_2_690x665.png)

f07_rho-ecdf__kodak_portra_400_hanatos2025_log_mse_perchan6_D55_3cab88db60a471c31457×1406 121 KB](/uploads/short-url/V8mEuO1f84gPH1ZoEaAq2ioUjy.png?dl=1)

[[![f06_xy-residual__kodak_portra_400_hanatos2025_log_mse_perchan6_D55_3cab88db60a471c3](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/b/bbba4dafb240564bb1d4194fe132bf0541728e4b_2_690x391.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/b/bbba4dafb240564bb1d4194fe132bf0541728e4b_2_690x391.png)

f06_xy-residual__kodak_portra_400_hanatos2025_log_mse_perchan6_D55_3cab88db60a471c31964×1114 346 KB](/uploads/short-url/qMIriw0humbWFLrqwr0limJnhrB.png?dl=1)

it works ok and as expected it is far from perfect, but generalizes well for typical non-spiky illuminants.

[[![f12_cross-illuminant__kodak_portra_400_hanatos2025_log_mse_perchan6_D55_3cab88db60a471c3](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/2/a2ff1e5b49995e1c3813d3cb59170343ac6c1af3_2_690x448.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/2/a2ff1e5b49995e1c3813d3cb59170343ac6c1af3_2_690x448.png)

f12_cross-illuminant__kodak_portra_400_hanatos2025_log_mse_perchan6_D55_3cab88db60a471c32188×1421 187 KB](/uploads/short-url/nfVWetGPOUBo4A8wa21qU7DbtKz.png?dl=1)

some film stocks behave a bit better, like for example **fujifilm_velvia_100**

[[![f04_sens-window__fujifilm_velvia_100_hanatos2025_log_mse_perchan6_D55_3cab88db60a471c3](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/b/0bb7644bb25942a749a70ea59ce160aa2e9cddbf_2_690x727.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/b/0bb7644bb25942a749a70ea59ce160aa2e9cddbf_2_690x727.png)

f04_sens-window__fujifilm_velvia_100_hanatos2025_log_mse_perchan6_D55_3cab88db60a471c31925×2029 326 KB](/uploads/short-url/1FEamUJo2dN92uqHjOukgCNauu3.png?dl=1)

[[![f06_xy-residual__fujifilm_velvia_100_hanatos2025_log_mse_perchan6_D55_3cab88db60a471c3](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/8/b80eecfb4183fe70f95b3e17f20d6f15d0f2debd_2_690x391.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/8/b80eecfb4183fe70f95b3e17f20d6f15d0f2debd_2_690x391.png)

f06_xy-residual__fujifilm_velvia_100_hanatos2025_log_mse_perchan6_D55_3cab88db60a471c31964×1114 353 KB](/uploads/short-url/qgfPD4Mim2fjM2moL9FVHNNoyYZ.png?dl=1)

[[![f07_rho-ecdf__fujifilm_velvia_100_hanatos2025_log_mse_perchan6_D55_3cab88db60a471c3](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/2/e2120c6593971015f0166dc72d53edd0ca4cccc7_2_690x663.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/2/e2120c6593971015f0166dc72d53edd0ca4cccc7_2_690x663.png)

f07_rho-ecdf__fujifilm_velvia_100_hanatos2025_log_mse_perchan6_D55_3cab88db60a471c31463×1406 120 KB](/uploads/short-url/wfUzLzTf3PpPLlu2BiSElCDP01N.png?dl=1)

but you are right that purple will suffer the most and will loose exposure, and very saturated purple might be quite problematic:

[[![f14_colorchecker_test__fujifilm_velvia_100_hanatos2025_log_mse_perchan6_D55_3cab88db60a471c3](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/f/af1c3190464bfd891d9cb8ecdb88e2ac69d34c49_2_690x247.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/f/af1c3190464bfd891d9cb8ecdb88e2ac69d34c49_2_690x247.png)

f14_colorchecker_test__fujifilm_velvia_100_hanatos2025_log_mse_perchan6_D55_3cab88db60a471c32194×788 93.8 KB](/uploads/short-url/oZ5XDmRr32r8gi3gpyspRaj7gHD.png?dl=1)

(i’m plotting corrected and uncorrected exposures as sRGB, i know it is blasphemy

[![:see_no_evil:](https://discuss.pixls.us/images/emoji/apple/see_no_evil.png?v=12)](https://discuss.pixls.us/images/emoji/apple/see_no_evil.png?v=12)

 but shows the directions of the corrections in fixing the patches)

but for kodak_portra_400 we still see an improvement for the color-checker-purple:

[[![f14_colorchecker_test__kodak_portra_400_hanatos2025_log_mse_perchan6_D55_3cab88db60a471c3](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/b/5b83642dd3606cdef86d2729e76b6993ac5989db_2_690x247.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/b/5b83642dd3606cdef86d2729e76b6993ac5989db_2_690x247.png)

f14_colorchecker_test__kodak_portra_400_hanatos2025_log_mse_perchan6_D55_3cab88db60a471c32194×788 96.4 KB](/uploads/short-url/d3yXaO97EPGzY3HzeLBzXjWXrfB.png?dl=1)

[small update]

i quickly computed the channel-averaged log_exposure shift across the xy plane int(sensitivitiy x upsampled_spectra x windows) / int(sensitivity x upsampled_spectra))) to show better the exposure change along the purple line for the two example stocks. this is also the exposure improvement we want for blues/reds, i.e. we are exposing them less with the bandpass that is optimized on the round trip error evaluated on the corpus. underexposure might be too much for very pure colors that are not in the corpus and not influencing the problem. even adding them in the optimization would probably not change much the overall improvements. it might add a bias towards broader bandpass filters, reducing the gains for typical gamut colors. thus the corpus should mimic the typical spectra we want to image, and we might just tollerate the problem on narrow band spectra on the purple line. i am pretty sure there must be smart ways to go around any of this, adding more complexity to it, but for now i am happy getting any small improvement we can get.

[[![f15_gain_map__kodak_portra_400_hanatos2025_log_mse_perchan6_D55_3cab88db60a471c3](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/2/629dbe1a8aef29ee68e5c509d5e8bc5cd4d9b5ba_2_330x330.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/2/629dbe1a8aef29ee68e5c509d5e8bc5cd4d9b5ba_2_330x330.png)

f15_gain_map__kodak_portra_400_hanatos2025_log_mse_perchan6_D55_3cab88db60a471c31167×1127 144 KB](/uploads/short-url/e4oKKzb8seSSqM1hwS714BtcTLI.png?dl=1)

[[![f15_gain_map__fujifilm_velvia_100_hanatos2025_log_mse_perchan6_D55_3cab88db60a471c3](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/7/a7b305b5a50350c43a69269252c7051fb37ade5e_2_330x330.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/7/a7b305b5a50350c43a69269252c7051fb37ade5e_2_330x330.png)

f15_gain_map__fujifilm_velvia_100_hanatos2025_log_mse_perchan6_D55_3cab88db60a471c31167×1127 130 KB](/uploads/short-url/nVxi2Ux5BGDx94NcHFrJzpixu2O.png?dl=1)

---

## #560 **Vicer Fx** (@Vicer_Fx) · 2026-04-27 22:44

One thing I see myself wanting to do when using the positive profiles is to change their white balance. I usually use the print filters when working with negatives. Would it be possible to do something similar for positives in the future?

Btw here are some tests I ran these days, I’ve been loving the program. Taken in raw with a not so great smartphone:

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/8/c8c162cab9446faedd99cfbc9a6aa7e47a6a5afe_2_690x912.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/8/c8c162cab9446faedd99cfbc9a6aa7e47a6a5afe_2_690x912.jpeg)

image975×1290 336 KB](/uploads/short-url/sDXOVMcxyN20EkO8CqvTrHJbrlA.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/8/f851abda516c5431cecc4bfec2926e725d21f151_2_690x919.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/8/f851abda516c5431cecc4bfec2926e725d21f151_2_690x919.jpeg)

image970×1293 316 KB](/uploads/short-url/zqJolfrRhVqgjo1DYAcL6Tx87Kx.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/1/91f4fe5c54b3f723843ca35fb72074ce0dddb385_2_690x920.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/1/91f4fe5c54b3f723843ca35fb72074ce0dddb385_2_690x920.jpeg)

image971×1295 247 KB](/uploads/short-url/kPc825ewK0MhtKR8AHRz1NBWmt7.jpeg?dl=1)

---

## #561 **Andrea** (@arctic) · 2026-04-28 04:47

> **@Vicer_Fx** (帖子 #560):
> One thing I see myself wanting to do when using the positive profiles is to change their white balance. I usually use the print filters when working with negatives. Would it be possible to do something similar for positives in the future?

even if printing of slide film is not (or was not

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 ) as diffused as the printing of negativea, positive print paper exists, and it is part of the plan to have it.

you can safely change the white balance when processing a raw for now, the printing process in the end is trying to solve a very similar problem but within the analog constraint of the analog media and analog tools. in my experience the results are fair, but since spektrafilm is following a purist approach, wb with the virtual enlarger will make me feel better.

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

great that you manage to get nice images with raw from a smartphone!

---

## #562 **Andrea** (@arctic) · 2026-04-29 21:28

i just dumped on the main repo a few updates from the last couple of weeks:

- better neutralized profiles. now kodak ultra endura is actually a nice paper that i feel wanna use. it was almost unusable before
- smoother diffusion filters and presets moking glimmerglass/black-pro-mist/pro-mist/cinebloom, for camera and enlarger
- band pass spectral filters optimized per stock for the spectral upsampler by hanatos, overall we have slightly better color reproduction of red and blues (they are less over exposed and over saturated), exposure error reduced from 20-15% to about 5-10% (rough estimates from round trip testing of exposures of real measured spectra)
- the inhibition coupler matrix for the negatives was tentatively refined algorithmically, still WIP
- better scattering halation model with possibility of stretching the highlights to recover possibly clipped irradiance of bright spots
- kodak verita 200d cine profile

not the cleanest development in the last weeks, but i was very driven and needed some fun. i will have to cleanup. i am not a real programmer, that was clear i guess

[![:laughing:](https://discuss.pixls.us/images/emoji/apple/laughing.png?v=12)](https://discuss.pixls.us/images/emoji/apple/laughing.png?v=12)

since there were several upgrades in the last month i decided to do some quick edits of nice photos and play-raws that i had laying around in random folders of my hard drive. for many of them i remember struggling to get good results with agx-emulsion in the past. every edit is mostly default except a handful of parameters reported below each pic. all the raws were loaded directly in spektrafilm and edited in 10-20 seconds and saved as preview (computation is still a pain point, and would have been longer than the edit!). no lovely grain texture

[![:cry:](https://discuss.pixls.us/images/emoji/apple/cry.png?v=12)](https://discuss.pixls.us/images/emoji/apple/cry.png?v=12)

.

i made extensive use of diffusion filters and I used only the kodak still family. they all share a very similar color soul, and the share the same dir couplers matrix. thus the saturation is somehow democratically distributed (I doubt this is the case for real life chemical recipes). after some use, you familiarize with the punchiness scale of the stocks. the constant dir coupler matrix is probably enhancing this gradient of saturation/contrast.

essentially in a scale of saturation and contrast they are roughly like this:

kodak portra 160

kodak portra 400

kodak portra 800

kodak gold - kodak ultramax

koadk ektar

and

kodak portra endura

kodak supra endura

kodak ektacolor edge (slightly older look)

kodak endura premier

kodak ultra endura (vintage look) is a bit of an outsider and it has a distinct character

a good ux would make this scale very explicit.

mix and matching film and paper according to need is a quick and dirty way to have an impressively immediate library of juicy looks. nothing new under the sun, I know, but familiarizing with them while editing makes you feel very confortable. for example portra film + portra paper is the most neutral and gentle. ektar + endura premier is super punchy on the opposite of the scale. when in need of even more or less saturation we still can cheat with virtual chemistry boosting or reducing of the couplers.

ektar + ultra endura is somehow surprised me, it’s a very good combination for photos that need a bit of character and are dull. gold + supra is the spektrafilm default and sits on the mid-upper of the punchiness stack.

here the edits:

[[![001](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/6/56c7091e77f7ea5ae94cbf281a976f44a5705a31_2_426x640.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/6/56c7091e77f7ea5ae94cbf281a976f44a5705a31_2_426x640.jpeg)

001682×1024 346 KB](/uploads/short-url/cnFuE7YNdHLpyLvM42bYbbllhRf.jpeg?dl=1)

001 - signature edits JaroslavKriz33_IMG_3475.CR2

wb as-shot, kodak ektar+ultra, 0Y0M 1.1PE, cinebloom 0.5

[[![002](https://d2x313g9lpht1q.cloudfront.net/original/3X/3/a/3aa9d9995bf98ee79319f03aedcc3d1286c90703.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/3/a/3aa9d9995bf98ee79319f03aedcc3d1286c90703.jpeg)

002426×640 176 KB](/uploads/short-url/8mXAU2KMOgx7vh3FcdUK7Oj4Esb.jpeg?dl=1)

002 - signature edits Signature Edits Free RawsIMG_5824.CR2

wb as-shot, -6Y-4M 0.9PE, kodak gold+supra

[[![003](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/2/02985129441973fc86c62186aee7cdc2851d0f41.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/2/02985129441973fc86c62186aee7cdc2851d0f41.jpeg)

003640×427 124 KB](/uploads/short-url/mXi956muPKtcueaW4jPDmYTP7X.jpeg?dl=1)

003 - signature edits Signature Edits free raw files tag <span class="mention">@signatureeditsco</span> IMG_4563.cr2

wb daylight, kodak gold+ultra, 0.86PE -4Y-2M, pro-mist 0.5

[[![004](https://d2x313g9lpht1q.cloudfront.net/original/3X/f/2/f2efbfb01878dbbc0f0c2a71c986814c6e34d300.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/f/2/f2efbfb01878dbbc0f0c2a71c986814c6e34d300.jpeg)

004640×427 160 KB](/uploads/short-url/yF7cQDGkWn2kxsYVsmNTvYFMYdq.jpeg?dl=1)

004 - signature edits Free Raw Files - Tag <span class="mention">@signatureeditsco</span> - _MG_2862.CR2

wb as-shot, kodak gold+supra, 1.1PE -10Y0M, enlarger pro-mist 0.5

[[![005](https://d2x313g9lpht1q.cloudfront.net/original/3X/1/e/1e49661d302eeb02128490971a81c79ce3d52b2c.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/1/e/1e49661d302eeb02128490971a81c79ce3d52b2c.jpeg)

005640×427 131 KB](/uploads/short-url/4jVzZq9RB6vFhf5ZuVgKgT48TBW.jpeg?dl=1)

005 - play raw 5D3_0104.CR2 [Difficult orange flower](https://discuss.pixls.us/t/difficult-orange-flower/27001)

wb as-shot, kodak portra160+supra, 1.4PE 5Y15M, couplers 0.75, glimmerglass 2

[[![006](https://d2x313g9lpht1q.cloudfront.net/original/3X/d/c/dc64abe14f6c72bd846dbb20d9a09df33c0a9dcf.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/d/c/dc64abe14f6c72bd846dbb20d9a09df33c0a9dcf.jpeg)

006640×426 123 KB](/uploads/short-url/vrGJjW5a8aTeBQxFwV8rsQyoxgb.jpeg?dl=1)

006 - play raw 20250225_0032.CR3 [Dealing with yellow color shift](https://discuss.pixls.us/t/dealing-with-yellow-color-shift/48530)

wb as-shot, kodak portra800+supra, 0.6PE 5Y0M, couplers 0.85

[[![007](https://d2x313g9lpht1q.cloudfront.net/original/3X/8/7/87dd572bdfcb59f08c41b9f512a43f57e5a29877.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/8/7/87dd572bdfcb59f08c41b9f512a43f57e5a29877.jpeg)

007640×427 94.8 KB](/uploads/short-url/jnUG3Fj1zDgQIneyUX5AyXR2Fmv.jpeg?dl=1)

007 - play raw 20240422_0008.CR2 [Fishing for a sunset](https://discuss.pixls.us/t/fishing-for-a-sunset/43275)

wb as-shot, kodak portra400+supra, 0.58PE 10Y0M, couplers 0.85, cinebloom 0.5

[[![008](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/a/5ad5f568e17cb363d3f29c6f6de98b130ac1f838.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/a/5ad5f568e17cb363d3f29c6f6de98b130ac1f838.jpeg)

008640×427 157 KB](/uploads/short-url/cXznlD0HD8GKZZ1cIFZDovUo5QI.jpeg?dl=1)

008 - play raw 7E4A0518.CR3 [[PlayRaw] Flower](https://discuss.pixls.us/t/playraw-flower/47431)

wb as-shot, kodak ultramax+supra, 1.5PE -2Y15M, enlarger black-pro-mist 0.5

[[![009](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/3/03dff35218c9e7f737ec3437cd63a82a619f796a.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/3/03dff35218c9e7f737ec3437cd63a82a619f796a.jpeg)

009640×424 125 KB](/uploads/short-url/yhf8fWEAyGXsajaDYbLdlz8gJQ.jpeg?dl=1)

009 - play raw IMGP2775.DNG [Pride orange smile, sharpness and color challenge](https://discuss.pixls.us/t/pride-orange-smile-sharpness-and-color-challenge/46225)

wb as-shot, kodak gold+supra, 0.5PE -5Y-2M, black-pro-mist 0.5

[[![010](https://d2x313g9lpht1q.cloudfront.net/original/3X/6/a/6a8d2a22c7e2639359120d2b194a1257199c30b1.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/6/a/6a8d2a22c7e2639359120d2b194a1257199c30b1.jpeg)

010640×427 137 KB](/uploads/short-url/fcB3rMiKPTddTdg9bB7xfb3cBH3.jpeg?dl=1)

010 - play raw _DSC5869.ARW [Golden Gate sunset](https://discuss.pixls.us/t/golden-gate-sunset/55098)

wb as-shot, kodak portra400+supra, 0.9PE 2Y-6M, couplers 0.74, glimmerglass 1

---

## #563 **Andrea** (@arctic) · 2026-04-29 21:33

[[![011](https://d2x313g9lpht1q.cloudfront.net/original/3X/b/5/b5fb8dfba633fd30482e1213e4eae6675c05cf3c.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/b/5/b5fb8dfba633fd30482e1213e4eae6675c05cf3c.jpeg)

011640×427 169 KB](/uploads/short-url/pXTnhcc4rQnnvRezdjMcwtGqsaM.jpeg?dl=1)

play raw - IMGP9542.DNG [Winter photo editing](https://discuss.pixls.us/t/winter-photo-editing/47259)

wb as-shot, kodak gold+supra, 0.76PE -1Y-2M, black-pro-mist 0.5

[[![012](https://d2x313g9lpht1q.cloudfront.net/original/3X/7/d/7d2488d5ce287e51a95dd0a52b671784b990a7b9.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/7/d/7d2488d5ce287e51a95dd0a52b671784b990a7b9.jpeg)

012640×427 128 KB](/uploads/short-url/hR3Xr0gKMcwqGZFLndMZbaRUBn3.jpeg?dl=1)

play raw - DSCF8379.raf [Playing with different light colors](https://discuss.pixls.us/t/playing-with-different-light-colors/48178)

wb as-shot, kodak gold+supra, 1PE 0Y0M (everything as default)

[[![013](https://d2x313g9lpht1q.cloudfront.net/original/3X/e/c/ecb72bd702353f6f4f1bbde7dd278ef7373f31b5.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/e/c/ecb72bd702353f6f4f1bbde7dd278ef7373f31b5.jpeg)

013640×427 138 KB](/uploads/short-url/xM57MSjZsYE93jO7YcWTb7MmEyF.jpeg?dl=1)

play raw - R0000418.DNG [Office building at night, London](https://discuss.pixls.us/t/office-building-at-night-london/43642)

wb tungsten, kodak vision3 500t+ultra, 0.5PE 5Y0M, highlights boost ev 10 boost range 0.5, halation (30%,0.5%,0) 200um, enlarger pro.mist 0.5

[[![014](https://d2x313g9lpht1q.cloudfront.net/original/3X/f/b/fb164903445ec78938dea1afd37ffcda10294df0.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/f/b/fb164903445ec78938dea1afd37ffcda10294df0.jpeg)

014640×427 127 KB](/uploads/short-url/zPdADtXZ2B5cNPkehoTR7iDQKXu.jpeg?dl=1)

play raw - 2024-02-25_12-13-25.NEF [Ocean Overlook to Play With](https://discuss.pixls.us/t/ocean-overlook-to-play-with/47407)

wb as-shot, koadk ektar+ultra, 0.8PE -12Y-2M, couplers 1.3

[[![015](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/7/5764fd79c7adfb65d9ecec6f4cfcd2351d985fa8.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/7/5764fd79c7adfb65d9ecec6f4cfcd2351d985fa8.jpeg)

015640×426 228 KB](/uploads/short-url/ct7UrdahEEvWPKijKEfS6NlAW4U.jpeg?dl=1)

play raw - 20250412_0039.ARW [Frame within a frame - #2 by Zbyma72age](https://discuss.pixls.us/t/frame-within-a-frame/49429/2)

wb as-shot, kodak ektar+ultra, 1PE 8Y3M

[[![016](https://d2x313g9lpht1q.cloudfront.net/original/3X/9/9/99fd498cc26750df8258e2cfb4cf633c5502be5c.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/9/9/99fd498cc26750df8258e2cfb4cf633c5502be5c.jpeg)

016426×640 193 KB](/uploads/short-url/lYfIy0BHgFM1j6ec9EAnw01iLHS.jpeg?dl=1)

paly raw - 2014-09-04_19-09-27.cr2 [A tree in the sun](https://discuss.pixls.us/t/a-tree-in-the-sun/43109)

wb as-shot, kodak ektar+ultra, 0.5PE 15Y5M, glimmerglass 1

[[![017](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/2/0299388c4c56f14360339932e06da592d8ce6ff9.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/2/0299388c4c56f14360339932e06da592d8ce6ff9.jpeg)

017640×427 192 KB](/uploads/short-url/mZecZiDJyLVkUPfqSbRAiFYpzH.jpeg?dl=1)

play raw - DSC_5188.NEF [Cologne train station by night](https://discuss.pixls.us/t/cologne-train-station-by-night/39092)

wb as-shot, kodak ektar-ultra, 0.5PE 30M5Y, black-pro-mist 0.5

[[![018](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/0/00b3ea80400c3455dbd5f65cab9e193bbc03bf90.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/0/00b3ea80400c3455dbd5f65cab9e193bbc03bf90.jpeg)

018640×427 122 KB](/uploads/short-url/6dt27xWbvJVkQYGTqXpo7PU6Pe.jpeg?dl=1)

play raw 20241031_0873.RAF [Dramatic Shadows Exercise](https://discuss.pixls.us/t/dramatic-shadows-exercise/47398)

wb as-shot, kodak ektar-ultra, 0.8PE -13Y-4M, pro-mist 0.5

[[![019](https://d2x313g9lpht1q.cloudfront.net/original/3X/a/c/ac626449496468395610de9c12c0d178f1ce710e.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/a/c/ac626449496468395610de9c12c0d178f1ce710e.jpeg)

019640×427 97.9 KB](/uploads/short-url/oAYVyd9kEQVnMOuknjIaKl3TORo.jpeg?dl=1)

play raw DSC07735.ARW [I have to share this with you all....](https://discuss.pixls.us/t/i-have-to-share-this-with-you-all/48259)

wb as-shot, kodak ektar+ultra, 0.6PE -16Y-12M, couplers 1.3

it is difficult to pinpoint where the improvement is, and a lot can be placebo, but i feel more “satisfaction” in the images than before when the band pass filter in the spetral upsapling was arbitrarily set, and not under control.

---

## #564 **Mica** (@paperdigits) · 2026-04-30 01:06

> **@arctic** (帖子 #562):
> i am not a real programmer

sorry chief, you have a working program with continual enhancements, and users to boot.

[![:wink:](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)

---

## #565 **None** (@lanidor) · 2026-04-30 10:28

Thanks [@arctic](/u/arctic) for the updates, colors look really good now! I wanted to ask, is there a way to tweak the grain behavior? Right now the blacks are, well, completely black, which isn’t something I see in my scanned images. I tried *Glare*, but it looks uniform and monochromatic. I’ll attach an example: the first is a digital image processed with Spektrafilm, the second is an inverted negative scanned on a Minolta Dimage Scan Elite 5400 II. I can provide more standalone examples, this is the only one where I shot the same scene on both digital and film.

[[![Spektrafilm](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/8/d8dc3d9ee239a0edf1a72e46f4b1eade02739fc5_2_690x460.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/8/d8dc3d9ee239a0edf1a72e46f4b1eade02739fc5_2_690x460.jpeg)

Spektrafilm7694×5138 2.84 MB](/uploads/short-url/uWqZP3nzQkZ5jaw6FgUETvuFmNn.jpeg?dl=1)

[[![Gold200-DimageScan5400II-q45](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/8/08b13ba939e9653dce01ac8c324519d6eeaab270_2_690x457.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/8/08b13ba939e9653dce01ac8c324519d6eeaab270_2_690x457.jpeg)

Gold200-DimageScan5400II-q457800×5168 3.44 MB](/uploads/short-url/1eTxt5ar8WdudeGAESmJ5Ob03pC.jpeg?dl=1)

---

## #566 **** (@Thomsen) · 2026-04-30 11:56

Nice work! Colors look very good. But the texture and ‘feel’ is a bit hard to evaluate with the low image-resolution and the camera diffusion filters.

Do you have any non-diffused high-res examples from the new model?

---

## #567 **Mateusz Grabowski** (@Mateusz_Grabowski) · 2026-04-30 14:21

These look stunning!

You changed my life and I am so grateful that I found this program.

Keep improving and exploring this at whatever pace you feel like

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

Again thank you very much for your work!

---

## #568 **Mateusz Grabowski** (@Mateusz_Grabowski) · 2026-04-30 15:10

I think I have found a bug with DIR couplers when selecting different slide films on the newest main branch version. Posted issue on the github page!

---

## #569 **None** (@Anthonygansauer) · 2026-04-30 23:51

[[![123](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/b/fb040249eb63766cbe2f7333d523bde5d1ae8cc8_2_690x862.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/b/fb040249eb63766cbe2f7333d523bde5d1ae8cc8_2_690x862.jpeg)

1231000×1250 1.17 MB](/uploads/short-url/zOAqV3wQNq2EWPZaZ2J9qvw2Hxe.jpeg?dl=1)

got it matching my style of how i print somewhat! this is such a nice program.

very soon will have a 1 of 1 comparison of a raw image through this process with portra 400 and fuji type ii with the same image shot on REAL portra 400 and printed on fuji type ii, cant wait to share

---

## #570 **Todd Prior** (@priort) · 2026-05-01 03:50

I really like the colors but I find it extremely dark???

---

## #571 **** (@Thomsen) · 2026-05-01 09:01

Beautiful! Are you using the digital enlarger diffusion?

---

## #572 **** (@mikae1) · 2026-05-01 10:15

> **@Anthonygansauer** (帖子 #569):
> got it matching my style of how i print somewhat! this is such a nice program.

Nice! What settings did you use for that look?

> **@priort** (帖子 #570):
> I really like the colors but I find it extremely dark???

A little dark, but a stylistic choice? In the age of digital many photographers (including me) are kind of stuck in distributing-the-data-over-the-histogram thinking, so to speak.

I think it’s fruitful to take more inspiration from traditional painters. Try to find anything even approaching the equivalent of 255/255/255 in Vermeer painting. The reasons for this are not only technical (aging, limited pigment range, cost of pigments).

[[![pieter-de-hooch-binnenplaats-met-rokende-man-en-drinkende-vrouw-mh0835-mauritshuis](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/d/5df2f78e159683b5de7d51373097b27ced8b9d1a_2_690x830.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/d/5df2f78e159683b5de7d51373097b27ced8b9d1a_2_690x830.jpeg)

pieter-de-hooch-binnenplaats-met-rokende-man-en-drinkende-vrouw-mh0835-mauritshuis1200×1444 1.62 MB](/uploads/short-url/dp6Xt3Xsr3IRlZXa6nyu1rYr0dI.jpeg?dl=1)

---

## #573 **Nuno Paulino** (@hatsnp) · 2026-05-01 10:24

It’s always a pleasure when restoration removes the 10 layer of varnish from these old paintings and the more natural hues show themselves.

---

## #574 **None** (@Anthonygansauer) · 2026-05-01 12:49

“extremely” dark? Maybe I’m just so used to this type of look, I don’t see it extremely dark, hard sunlight you either commit to shadows or highlights and I’d rather commit to highlights.

---

## #575 **None** (@Anthonygansauer) · 2026-05-01 12:51

Couldn’t have said it any better Sargent, Vermeer, Eakins, Manet are such huge inspirations for how I print and compose!

---

## #576 **Todd Prior** (@priort) · 2026-05-01 14:01

I was looking on it on my calibrated monitor and several of the faces are essentially in total darkness…so maybe issues on my end, or the chosen brightness of your monitor is high or at least higher than mine, or its exactly as you intend and that is that… it was just an observation…

---

## #577 **** (@europlatus) · 2026-05-01 16:48

> **@priort** (帖子 #576):
> several of the faces are essentially in total darkness…so maybe issues on my end

All faces are visible on my screen. It does sound like an issue at your end.

---

## #578 **Todd Prior** (@priort) · 2026-05-01 17:35

Ya I will have to check I run a pretty standard 120 cd/m2

---

## #579 **Mateusz Grabowski** (@Mateusz_Grabowski) · 2026-05-01 18:04

Wanted to share some of my photos edited using spektrafilm

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 Some are 6 months old! It is unfortunate that I dont have raw files for some of them so we could check how the simulation has improved.

My goal was to create look of a high quality medium format film scans with very little grain rather than authentic darkroom prints. Enjoy!

<div class="lightbox-wrapper">[[![2](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/7/a712c707641725f7199a8fb1ebf91489f8e7df68_2_689x472.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/7/a712c707641725f7199a8fb1ebf91489f8e7df68_2_689x472.jpeg)

24960×3400 676 KB](/uploads/short-url/nPZY1iAfvFtPslXIvYJ5yjDG2DK.jpeg?dl=1)

[[![16](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/2/72af90cc6f0f0108b8f1a0edbafe928096b7c002_2_690x912.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/2/72af90cc6f0f0108b8f1a0edbafe928096b7c002_2_690x912.jpeg)

163032×4009 463 KB](/uploads/short-url/gmyzUA9TD6VJiuRNuf3uhI3QdmG.jpeg?dl=1)

[[![21](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/5/c5ff52e97c18dc6b4bd4ad4b472b0780a4b46041_2_690x527.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/5/c5ff52e97c18dc6b4bd4ad4b472b0780a4b46041_2_690x527.jpeg)

214248×3246 852 KB](/uploads/short-url/sfz5C6ymaO11Y34cLlW950dhofT.jpeg?dl=1)

[[![output41](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/c/3c45e70f77d36daf7a1675348b6a860268544213_2_690x504.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/c/3c45e70f77d36daf7a1675348b6a860268544213_2_690x504.jpeg)

output414630×3382 1.12 MB](/uploads/short-url/8BcpEHjNNplvfjUZt4z2QQrbEaL.jpeg?dl=1)

</div>

---

## #580 **** (@mino) · 2026-05-01 18:47

Those are beautiful, thanks for sharing :-)! The urban shot is 100% from the level Venice from Tony Hawks Pro Skater 2 ;-).

---

## #581 **Mateusz Grabowski** (@Mateusz_Grabowski) · 2026-05-01 19:19

I would post more but since I am a new member on this forum I can’t hah!

---

## #582 **Andrea** (@arctic) · 2026-05-01 23:05

> **@lanidor** (帖子 #565):
> wanted to ask, is there a way to tweak the grain behavior

i will try to work on the grain in the future, it hasn’t received the same love that other part of the model had. you can try to boost `grain >> density_min` that will add more fog, i.e. grain in the unexposed part of the image. although, when printing on the virtual paper you might not see a big change because in a correctly exposed negative and print the dynamic range fits more or less in the linear part of the negative curves.

> **@Thomsen** (帖子 #566):
> Do you have any non-diffused high-res examples from the new model?

yeah, i will post a couple of problematic images that might show a difference in a before/after comparison

> **@Anthonygansauer** (帖子 #569):
> got it matching my style of how i print somewhat! this is such a nice program.

that look stunning, i am very grateful for the suggestion of exploring the diffusion filter in the enlarger.

i am very grateful for all the feedback in general by everyone here, it that has sprouted a ton of great ideas.

> **@Anthonygansauer** (帖子 #569):
> very soon will have a 1 of 1 comparison of a raw image through this process with portra 400 and fuji type ii with the same image shot on REAL portra 400 and printed on fuji type ii, cant wait to share

that sound very useful, i am curious to see more comparisons!

> **@Mateusz_Grabowski** (帖子 #567):
> You changed my life and I am so grateful that I found this program.

i am absolutely flattered by this comment

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

> **@Mateusz_Grabowski** (帖子 #579):
> My goal was to create look of a high quality medium format film scans with very little grain rather than authentic darkroom prints.

cool pictures, thanks for sharing. theoretically speaking, changing the film size from 35mm to 70mm (or the size of the film you are aiming for) should take into account the scaling of the grain, in a physically meaningful way. in the sense that if you think the 35mm grain is plausible with a certain set of parameters then changing film size will give you that rendering for the bigger film.

---

## #583 **Aedan** (@chaert-s) · 2026-05-01 23:45

Hey all,

this looks like an amazing project! Coincidentally I was pondering developing a very similar tool myself, seems I may just hop onto the bandwagon here!

Right off the bat, I wanted to say hats off, this looks really incredible! Thank you so much for putting in the work and dedication to make such a precise and true-to-reality tool!

One thought I had was, you could possibly improve the accuracy of the grain simulation. “Realistic Film Grain Rendering” and “A Stochastic Film Grain Model for Resolution-Independent Rendering”, both by Newson et al. came to mind here. They have a very grounded approach. I haven’t gotten too deep into your code but it seems you may already be taking some elements from those papers, however the costly Monte Carlo estimation is left out as it seems? Adding that for a “final quality” render might improve grain results?

The second thing that came to mind was porting this over to C#/C++ for faster inference. Python is a great language and super fast to set up, however it comes at the cost of memory bloat and slower execution.

With your permission I would like to attempt to port this awesome tool over to a C variant and try my luck to maybe even get this running for video as a true film simulation tool for lets say Davinci Resolve or other video editing programs?

All the best,

Aedan

---

## #584 **Yogansh Bhatt** (@Yogansh_Bhatt) · 2026-05-02 03:03

VKDT works beautifully! Those GPU shaders are FAST . You might have wanna have a look at filmsim which is the ported module there.

---

## #585 **Ryan Cara** (@Ryan_Cara) · 2026-05-02 03:24

I’ve been working on little tool that exports a LUT (taken from ART’s spektrafilm_mklut.py script) from a json preset made in Spektrafilm if anyone wants to give it a crack. I wanted to use them on some upcoming video shoots.

<aside class="onebox githubrepo" data-onebox-src="https://github.com/ryancara/Spektrafilm-LUT-Generator">
 <header class="source">

 [github.com](https://github.com/ryancara/Spektrafilm-LUT-Generator)
 </header>

 <article class="onebox-body">




[![图片594](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/8/0809706a8090d3db85d31b732f21a06f98928269.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/8/0809706a8090d3db85d31b732f21a06f98928269.png)


### [GitHub - ryancara/Spektrafilm-LUT-Generator: Generates a CLF or Cube LUT from Arctic's...](https://github.com/ryancara/Spektrafilm-LUT-Generator)


<span class="github-repo-description">Generates a CLF or Cube LUT from Arctic's Spektrafilm spectral film simulation app.</span>

 </article>









</aside>

Could be a cool feature to add within Spektrafilms GUI

[![:blush:](https://discuss.pixls.us/images/emoji/apple/blush.png?v=12)](https://discuss.pixls.us/images/emoji/apple/blush.png?v=12)

---

## #586 **Mateusz Grabowski** (@Mateusz_Grabowski) · 2026-05-02 06:58

Yes LUT export is very much needed in my opinion. I have managed to create haldclut and convert it to cube lut but only in srgb colorpsace so far. Looks great on videos in Davinci Resolve!

Also, it would be nice to bypass film simulation and leave print simulation only. I do shoot film and had an idea yesterday that it would be great to import linear DSLR scan of a negative into spektrafilm and just use print paper simulation!

That or ability to export just print lut and apply it in other software

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

Of course ability to export just the film lut without print would be much appreciated

[![:slightly_smiling_face:](https://discuss.pixls.us/images/emoji/apple/slightly_smiling_face.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slightly_smiling_face.png?v=12)

 maybe in Cineon Film Log as well.

---

## #587 **jo** (@hanatos) · 2026-05-02 08:23

> **@Ryan_Cara** (帖子 #585):
> exports a LUT

keep in mind that a lut can’t encode some of the non-global effects (couplers, halation, grain).

> **@Yogansh_Bhatt** (帖子 #584):
> VKDT works beautifully! Those GPU shaders are FAST

thanks

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 vkdt takes 15ms with couplers, grain, and halation on a 16MP image (RTX 4080S). not sure what output video res you’re targeting, at 2k this is single-digit milliseconds. vkdt has ffmpeg/prores input and output, if you encounter any hickups with specific video formats let me know.

---

## #588 **Ryan Cara** (@Ryan_Cara) · 2026-05-02 08:23

I really tried to get HALDs to work too, but couldn’t figure out the colourspace thing. Also I believe you can bypass the print and just grab a LUT of the film stock

[![:slightly_smiling_face:](https://discuss.pixls.us/images/emoji/apple/slightly_smiling_face.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slightly_smiling_face.png?v=12)

 (not vice versa though).

---

## #589 **** (@Thomsen) · 2026-05-02 11:31

I hereby present - the Queen of Norway on spectral film simulation.

[[![Queen](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/1/51c3b915c43749b12a727db16d7915704dcbd131_2_690x459.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/1/51c3b915c43749b12a727db16d7915704dcbd131_2_690x459.jpeg)

Queen5000×3327 2.37 MB](/uploads/short-url/bFk0BbPrW3x43iBrR6AUwpQAtYR.jpeg?dl=1)

(Her jacket was a nuissance, overexposing the red channel like crazy. Helped to pull it back with the ych chromacity vs chromacity curves in VKDT).

---

## #590 **** (@mino) · 2026-05-02 12:13

seems like [@arctic](/u/arctic) earned the badge “*internationally and royally recognized*”. Neat photo

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 !

---

## #591 **Ryan Cara** (@Ryan_Cara) · 2026-05-02 12:17

> **@hanatos** (帖子 #587):
> keep in mind that a lut can’t encode some of the non-global effects (couplers, halation, grain).

Are all the coupler parameters non-global? I assumed that the “amount” slider (DIR Global Multiplier) was LUT encodable (As in ART)?

Grain, halation and diffusion are already not being taken into account.

I do really need to test out video in VKDT!

---

## #592 **Mateusz Grabowski** (@Mateusz_Grabowski) · 2026-05-02 12:50

There are some parameters that affect sharpness. I just set them to 0 and luts seem to work perfectly fine. I haven’t stress tested them though.

---

## #593 **None** (@Anthonygansauer) · 2026-05-02 19:37

[[![Low Res01](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/d/1d0404981e2b2f702af5d1f9219b81af6e30eb7d_2_690x862.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/d/1d0404981e2b2f702af5d1f9219b81af6e30eb7d_2_690x862.jpeg)

Low Res011000×1250 1.22 MB](/uploads/short-url/48GsddQKds41vpMUxHAazs0g4Ut.jpeg?dl=1)

[[![Low Res 02](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/5/1510681b701fd267c79fcb5c45c527ff42fae2a4_2_690x862.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/5/1510681b701fd267c79fcb5c45c527ff42fae2a4_2_690x862.jpeg)

Low Res 021000×1250 822 KB](/uploads/short-url/30lb2fyOWU1yQzvSGowNU2WggFm.jpeg?dl=1)

one is digital raw than spektral, one is a film darkroom print, all adjustments for the digital were made in program with some minor split tone tweaks in photoshop! this is jawdropping stuff

---

## #594 **None** (@Anthonygansauer) · 2026-05-02 19:43

oh and i matched the borders too in photoshop, and sharpened it to match 6x7 detail.

[[![low res raw](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/9/e98625159c33bbe75887302c62e712e90ac6ae07_2_690x862.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/9/e98625159c33bbe75887302c62e712e90ac6ae07_2_690x862.jpeg)

low res raw1000×1250 706 KB](/uploads/short-url/xjQEAukM3p9dkWLUdto3P6SdQbl.jpeg?dl=1)

and heres the normalized raw

---

## #595 **None** (@Anthonygansauer) · 2026-05-02 19:45

[[![film scan low res](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/a/1ab90920980e84428fcbdfb15082d1298a99ef74_2_690x845.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/a/1ab90920980e84428fcbdfb15082d1298a99ef74_2_690x845.jpeg)

film scan low res1000×1226 1.19 MB](/uploads/short-url/3OoQMmw7nobIaUWRZ31zF9we9FO.jpeg?dl=1)

and now film scan on a noritsu scanner

---

## #596 **WG** (@BPH3647) · 2026-05-02 22:06

This makes me wish I splurged on a densitometer back when I was sorting out my control strip process.

[@arctic](/u/arctic) Quick question about exporting/saving:

Is there a way to designate which filetype to save as? I’m on M1 Mac, Main branch before the positive film coupler fix. It usually saves as a .png but it also has a strange habit of choosing .jpg seemingly at random. Early versions exported a .tif, hoping to get back to that as it matched my workflow.

---

## #597 **WG** (@BPH3647) · 2026-05-02 22:14

[@Anthonygansauer](/u/anthonygansauer) You beat me to the punch with the comparisons! Great stuff! How much are you finding you have to go in and play with the finicky settings (couplers/ir and uv filters)?

Would be fun to trade some of the Json settings files.

---

## #598 **None** (@Anthonygansauer) · 2026-05-03 00:25

Wasn’t too much editing! A lot of preflash, more than I would’ve thought. I’ll make a google drive of the raw and print so others can play with it. I’ll also link my saved settings in a file when I get back to my computer

---

## #599 **jo** (@hanatos) · 2026-05-03 08:28

> **@Ryan_Cara** (帖子 #591):
> Are all the coupler parameters non-global?

well the couplers diffuse a bit and only then do their thing/affect colours.

> **@Ryan_Cara** (帖子 #591):
> I assumed that the “amount” slider (DIR Global Multiplier) was LUT encodable (As in ART)?

sorry no idea how that is done in ART. maybe just the diffusion is left away/assumed to stay sub-pixel.

---

## #600 **Andrea** (@arctic) · 2026-05-03 11:50

> **@chaert-s** (帖子 #583):
> “Realistic Film Grain Rendering” and “A Stochastic Film Grain Model for Resolution-Independent Rendering”, both by Newson et al. came to mind here.

hey Aedan, welcome to the forum

i did read in depth the paper, and i think it is wonderful work. it has many strengths, but also shortcomings (by the way, happy to discuss in depth about it

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 ). the implementation in spektrafilm is at some level simplified and in other aspects much more advanced. the ultimate goal is to match the measured diffuse rms granularity curves of real film, the ultimate film grain look, the real truth.

For example the following from kodak vision3 250d:

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/8/3/8315b9bc08f02575641138325a63b3ae34062b10.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/8/3/8315b9bc08f02575641138325a63b3ae34062b10.png)

image608×567 28.9 KB](/uploads/short-url/iHD5Ux95J3ZiluUJVB1ZQCGlvfW.png?dl=1)

the model form Newson et al. is kind of impressive in the way they set up the resolution independent problem, but they miss in fine tuning the model to real data. in doing so you realize pretty quickly that you need the surrounding parts of the film simulation, at least if you want to work “in the right representation/pipeline step” with color film. the application to color showcased in the paper is very rushed and i would believe it might be pretty far from measured diffuse granularity.

this endeavor towards better grain was also my entry point, and it is the very short summary of the early history of my efforts in this toy project.

> **@chaert-s** (帖子 #583):
> The second thing that came to mind was porting this over to C#/C++ for faster inference.

i see the python implementation as a quick and dirty test bench. the model is still in heavy development. in the last weeks i changed parameters input in the gui every other sunset

[![:rofl:](https://discuss.pixls.us/images/emoji/apple/rofl.png?v=12)](https://discuss.pixls.us/images/emoji/apple/rofl.png?v=12)

 and python gives to someone like me a way to do it. I have been focusing more on the math and the concepts for now (and got unbelievable amount of smart feedback and ideas, by having my little crappy gui and a an amazing place like pixls.us to share).

the super vkdt implementation by [@hanatos](/u/hanatos) is the best possible performance i could think of, three orders of magnitude faster than the python implementation

[![:exploding_head:](https://discuss.pixls.us/images/emoji/apple/exploding_head.png?v=12)](https://discuss.pixls.us/images/emoji/apple/exploding_head.png?v=12)

anyway good ideas are always good ideas, and i am pretty sure it would be cool to explore the video side of it. just my driving force has been photography for now, because it is also my hobby.

> **@Thomsen** (帖子 #589):
> I hereby present - the Queen of Norway on spectral film simulation.

this stole me a nice smile

> **@Anthonygansauer** (帖子 #593):
> one is digital raw than spektral, one is a film darkroom print, all adjustments for the digital were made in program with some minor split tone tweaks in photoshop! this is jawdropping stuff

kind of amazing! thank you so much for bringing this kind of data and comparison. i see the color of the shirt a little different and some other small shifts, but overall quite amazing. and lovely photos and subject too! in a dream world, having this kind of sim/real data could let us implement simple strategies for color tuning, in principle at least. not sure we want to open that pandora box though. as a very simple first step, having this comparison is arguably the best way to verify the general amount of inhibition couplers.

lovely anyway [@Anthonygansauer](/u/anthonygansauer) !

> **@BPH3647** (帖子 #596):
> Is there a way to designate which filetype to save as?

right now if you add the extension to the file name it will save in that format. i recently flipped the default from png to jpg. i think it is a more sensible default for saving high res images. but it would be easy to add a default format output somewhere. i took a note about it.

> **@Anthonygansauer** (帖子 #598):
> A lot of preflash

that’s very interesting and fits in the discussion about the paper base >> something could be done there

> **@BPH3647** (帖子 #534):
> This is a comparison I made while trying to sort out discrepancies between Endura rolls with a supplier.
Kodak-Kodak-Compare-021364×1800 1.22 MB

> **@hanatos** (帖子 #599):
> sorry no idea how that is done in ART

ART is bypassing all the non-local and stochastic effects computing a lut, essentially encoding only the “average” output of a flat field (minus the glare that is only stochastic for now).

---

## #601 **Andrea** (@arctic) · 2026-05-03 12:07

> **@Thomsen** (帖子 #566):
> But the texture and ‘feel’ is a bit hard to evaluate

here are some full resolution crops done with the new model:

(i added long range coupler diffusion by the way, still uncommited. it keeps the mtf raised a few point percent at low frequency, and takes into accounts Levy style diffusion due to inhomogeneity or diffusion through the developer, if you look closely you will see a touch of local contrast from the long range diffusion of inhibition couplers).

[[![no_coupler_diffusion_no_halation-scattering](https://d2x313g9lpht1q.cloudfront.net/original/3X/4/0/40f605d5563a2e6b2e63e13c4f2b3c21b34968c2.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/4/0/40f605d5563a2e6b2e63e13c4f2b3c21b34968c2.png)

no_coupler_diffusion_no_halation-scattering563×563 637 KB](/uploads/short-url/9gFET6ObVi62EBahAf9QwjyWJO2.png?dl=1)

[[![only_halation-scattering](https://d2x313g9lpht1q.cloudfront.net/original/3X/4/e/4e7f86a94f1adb63f445b15afcad2db38a0f14ce.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/4/e/4e7f86a94f1adb63f445b15afcad2db38a0f14ce.png)

only_halation-scattering563×563 628 KB](/uploads/short-url/bcqsT3jso9SsQiom2GRYj0HGav4.png?dl=1)

[[![full_diffusion_model](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/0/0050722925c9020f3fb359fb00ea5a176ce9e80c.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/0/0050722925c9020f3fb359fb00ea5a176ce9e80c.png)

full_diffusion_model563×563 630 KB](/uploads/short-url/2MlZcOy00RMW0GWEPKa3Tn9vDm.png?dl=1)

(left) no diffusion effects, (middle) only halation/scattering, (right) full diffusion model.

[[![only_dir_coupler_diffusion](https://d2x313g9lpht1q.cloudfront.net/original/3X/7/b/7b8ba22b27a5a1e5ac2392b08830dd92703776fb.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/7/b/7b8ba22b27a5a1e5ac2392b08830dd92703776fb.png)

only_dir_coupler_diffusion563×563 646 KB](/uploads/short-url/hCVTjBycS7cm0tY9vNMwKg1b0bp.png?dl=1)

here is only dir couplers diffusion and no halation/scattering for reference.

for now the current defaults are based on rough tuning of the model to my trusty reference portra 400, but we could do so much more of course, like modern/vintage/old presets, or profiling semi automatically all the stocks. these days i just would like to have 48 hours per day, and not to have to care of having a job to buy me food

[![:rofl:](https://discuss.pixls.us/images/emoji/apple/rofl.png?v=12)](https://discuss.pixls.us/images/emoji/apple/rofl.png?v=12)

and here is a comparison of the portra 400 data-sheet mft, and a simulated measurement of the mtf from the model

[[![mtf_kodak_portra_400](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/3/c356c71cb374353073f7066fa26761abb06b8df3.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/3/c356c71cb374353073f7066fa26761abb06b8df3.png)

mtf_kodak_portra_400560×562 23.6 KB](/uploads/short-url/rS31GQXNSUeSNAU58ckuKpAA25R.png?dl=1)

[[![mtf_simulated_kodak_portra_400_mod0.2_2-100cy](https://d2x313g9lpht1q.cloudfront.net/original/3X/1/2/12a39c11fdf33611e1dc8bd25098cfb48215753b.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/1/2/12a39c11fdf33611e1dc8bd25098cfb48215753b.png)

mtf_simulated_kodak_portra_400_mod0.2_2-100cy630×630 39.5 KB](/uploads/short-url/2ET7QmArvOwTsw87mXR3aKf5rnR.png?dl=1)

---

## #602 **** (@slazaar) · 2026-05-04 09:01

Hi everyone,

Firstly, I just wanted to say how much I appreciate this project and the incredibly informative discussions here - it’s been a great resource while getting up to speed.

I have a beginner question that might also be helpful for others, especially with the recent updates.

From the README, my understanding is the recommended workflow:

**RAW → darktable → 32-bit float TIFF (linear, no filmic/sigmoid, ProPhoto RGB)**

This works as expected with RAW files (no conversion).

However, I’m unsure about my TIFF workflow and whether I’m introducing an issue earlier on.

Currently I’m doing:

**RAW → Photoshop → Adobe RGB TIFF → darktable → linear ProPhoto RGB**

When importing these TIFFs via *import rgb*, the results seem off - so I’m wondering if the Photoshop step (and Adobe RGB conversion) is causing a mismatch with the expected input.

[[![Screenshot 2026-05-04 at 6.59.46 PM](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/9/e94f07fe7e78087db6c7cff694f4af0097cc685c_2_689x463.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/9/e94f07fe7e78087db6c7cff694f4af0097cc685c_2_689x463.png)

Screenshot 2026-05-04 at 6.59.46 PM2558×1718 2.6 MB](/uploads/short-url/xhWzBmTQGy0H0yRymLtlzXNszbm.png?dl=1)

It would be really helpful to clarify this, as I imagine a few people would like to have the workflow of retouching on Photoshop and experimenting with spectral film as a final finish.

Thanks again for all the work and knowledge shared here - really appreciate any guidance!

---

## #603 **Ryan Cara** (@Ryan_Cara) · 2026-05-04 12:14

I think it’d be a lot easier to do your Photoshop work after Spekatrafilm if possible. Spektrafilm can now load RAW files.

If you’re keen on using Photoshop before Spektra there’s a few steps you probably need to take first. When importing a RAW into Photoshop, it opens “Camera Raw” - Make sure you use a Linear Camera profile. After that, you’d need to make sure it’s opening into Photoshop in the right colourspace/gamma so you’re staying scene referred (this is usually at the bottom of the Camera Raw window I think…or there’s a setting cog).

After that you’d need to export from Photoshop and also stay scene referred. So Linear/Prophoto? Then you can import that into Spektra.

I think it’d be pretty hard to work in Photoshop on a scene linear photo though, unless it’s applying a viewing transform!

Edit: It’s not as involved as I thought. I’ve uploaded a little video showing the process. You’ll need a linear camera profile. I’m using one from Cobalt, but it’s not too difficult to make your own.

(Also I didn’t show it in the video, but you’ll need to change your input color-space in Spektrafilm to ACES2065-1):

<aside class="onebox googledrive" data-onebox-src="https://drive.google.com/file/d/1zOHb2yeEPDe_SleImqx_6pvzAFIMPlUv/view?usp=share_link">
 <header class="source">

 [drive.google.com](https://drive.google.com/file/d/1zOHb2yeEPDe_SleImqx_6pvzAFIMPlUv/view?usp=share_link)
 </header>

 <article class="onebox-body">
 [](https://drive.google.com/file/d/1zOHb2yeEPDe_SleImqx_6pvzAFIMPlUv/view?usp=share_link)

### [How to.mov](https://drive.google.com/file/d/1zOHb2yeEPDe_SleImqx_6pvzAFIMPlUv/view?usp=share_link)

Google Drive file.

 </article>









</aside>

---

## #604 **None** (@Anthonygansauer) · 2026-05-04 15:22

[[![dwonsized](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/e/1eb39be1330a607409334082dca5dfe8a1b9340c_2_690x552.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/e/1eb39be1330a607409334082dca5dfe8a1b9340c_2_690x552.jpeg)

dwonsized1000×800 953 KB](/uploads/short-url/4nB8kHvQm77n50CeixVTjwamFpG.jpeg?dl=1)

just incredible

---

## #605 **None** (@Anthonygansauer) · 2026-05-04 15:34

[https://drive.google.com/drive/folders/1ryifCcPHbDQoFiofn46u1Wiymi4RoxdE?usp=sharing](https://drive.google.com/drive/folders/1ryifCcPHbDQoFiofn46u1Wiymi4RoxdE?usp=sharing)

heres a google drive so you guys can match and play with it yourself!

It includes:

RA4 print using Pentax 67ii + 105mm f2.4 + Portra 400 + Fuji DPii Paper scanned by a Epson V600

Film scan of the same frame using a Noritsu HS-1800 scanner.

Digital raw from a Lumix S5ii using a 50mm f1.4 of identical frame.

GUI parameter preset to import for matching the print to print emulation settings.

---

## #606 **None** (@Anthonygansauer) · 2026-05-04 15:53

[[![For group](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/f/9f73cd1b6fd6003fa84a78a74be0a822134e24f7_2_690x862.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/f/9f73cd1b6fd6003fa84a78a74be0a822134e24f7_2_690x862.jpeg)

For group1000×1250 760 KB](/uploads/short-url/mKA1hG3cUTtOOYxJgl0zk14zEZ9.jpeg?dl=1)

[[![Digital Emulation _2](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/8/785a8afaec38aa4f0cbfa9f04f2b2095f977d78d_2_690x862.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/8/785a8afaec38aa4f0cbfa9f04f2b2095f977d78d_2_690x862.jpeg)

Digital Emulation _21000×1250 1.2 MB](/uploads/short-url/haHhAyyuNtSjZEaQfgx6QWslO3P.jpeg?dl=1)

another test

top is real film + RA4 print scaned

bottom is digital emulation.

all editing was matching black point

---

## #608 **** (@Cristian) · 2026-05-04 16:17

Great! Can you please share your GUI parameter preset for this photo?

---

## #610 **None** (@Anthonygansauer) · 2026-05-04 16:50

It’s the same one in the google drive !

---

## #611 **** (@Cristian) · 2026-05-04 17:00

Thank you!

---

## #612 **None** (@Anthonygansauer) · 2026-05-04 17:50

[[![IMG_6798](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/f/9f0d6b74d2d2eca7129e3cd3323e0a1b2e3464bc_2_690x504.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/f/9f0d6b74d2d2eca7129e3cd3323e0a1b2e3464bc_2_690x504.jpeg)

IMG_67981284×939 1.54 MB](/uploads/short-url/mH2FvvgASoNrzbqnapvaaPwwWQs.jpeg?dl=1)

[

And just for fun here is a Ektachrome 100 emulation. I made this one myself shooting -5EV to +5EV color charts between my Lumix S5ii shooting Vlog and my Nikon F4 using Ektachrome and matching them. The great thing about Lumix S5 series is you can use 3Dluts for stills. This image is straight out of camera. Basically infinite ekatchrome! I have yet to test 1:1 but soon!

---

## #613 **Mateusz Grabowski** (@Mateusz_Grabowski) · 2026-05-04 18:45

Oh wow! I have S5IIX so that 3Dlut feature might be of use. Currently using it only for preview in video.

My only 2 120 rolls of Velvia 50 and E100 are waiting for some special ocasion

[![:wink:](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)

---

## #614 **Mateusz Grabowski** (@Mateusz_Grabowski) · 2026-05-04 18:52

Here is a video I made yesterday using exported haldcluts from spektrafilm. With couplers included!

 <iframe src="https://www.youtube.com/embed/_MZatpGIlRo?feature=oembed&wmode=opaque" width="480" height="360" frameborder="0" allowfullscreen="" class="youtube-onebox" seamless="seamless" sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox allow-presentation"></iframe>

Everything was recorded on lumix s5iix with 5000K white balance in V-Log using Helios 44-2 lens.

only LUT used was Kodak 200D printed on 2393.

Adjusted only exposure, contrast and pivot in Davinci Resolve plus some gate weave and halation. Minor saturation and printer lights adjustments on some clips. Skipped grain because no matter what I do I can’t get to look good past YT compression. Enjoy!

---

## #615 **** (@mikae1) · 2026-05-04 19:58

> **@arctic** (帖子 #601):
> these days i just would like to have 48 hours per day, and not to have to care of having a job to buy me food

If this project would get some more exposure, I’m confident this wouldn’t be an unattainable goal with some crowdfunding. But I guess that also comes with new expectations from funders (that are not always familiar with open source software development).

> **@Ryan_Cara** (帖子 #603):
> I think it’d be a lot easier to do your Photoshop work after Spekatrafilm if possible. Spektrafilm can now load RAW files.

This will be a lot less flexible and push values outside the “boundaries” that Spektrafilm sets.

The way I do it is I edit in darktable as usual, with sigmoid turned on. After/over `sigmoid` I place the `LUT 3D` module with a Portra 400 NC- LUT. Then I do perspective correction, denoising and dodging and burning in darktable using a combination of masked `tone equalizer` and `rgb curve` modules. When I’m ready I disable `sigmoid` and `LUT 3D` and `color balance rgb` and export to 32 bit (float) OpenEXR in linear ProPhoto RGB that I then open in Spektrafilm. Works very well, but is a bit cumbersome. At least it’s less cumbersome than the actual darkroom.

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 One day I still hope to see Spektrafilm in darktable…

---

## #616 **None** (@sahuaro.senorita) · 2026-05-04 20:30

hi all, potentially dumb question here, but i finally (seemingly) managed to get this installed on my mac using uv. after it was completed the terminal says “Installed 1 executable: **spektrafilm**”–however i have no clue where to find this executable or know how to run it. sorry if it’s obvious, but what’s the next step? how do i find & run this?

---

## #617 **** (@mikae1) · 2026-05-04 20:35

> **@sahuaro.senorita** (帖子 #616):
> how do i find & run this?

Like so:

> **@arctic** (帖子 #525):
>
```
uvx --from git+https://github.com/andreavolpato/spektrafilm.git@dev spektrafilm

```

---

## #619 **Ryan Cara** (@Ryan_Cara) · 2026-05-04 23:36

I do agree, but Salazar wanted to use Photoshop prior to Spektrafilm for retouching work! Does the method I provided push things outside of the boundaries? If so, [@slazaar](/u/slazaar), it might be worth going Darktable (Export Prophoto RGB Linear) → Photoshop → Spektrafilm. The conversion from Prophoto RGB (With a gamma of 1.8) to ACES 2065-1 is probably not ideal, but unfortunately Camera Raw seems to be lacking a few options when it comes to this.

---

## #620 **** (@slazaar) · 2026-05-05 02:04

Super helpful - thanks both (+mikae1)

I’m still pretty new to darktable, but it’s been really interesting seeing how much control it gives over the RAW pipeline.

I usually work out of Capture One, but my understanding is that it doesn’t offer a truly scene-linear workflow in the same way except for an option for a linear curve (and I think the same applies to Camera Raw as well), so this opens up a different way of approaching things.

I’ll try a few of the methods suggested - great to have some options beyond the usual C1 / Camera Raw route for prepping files.

---

## #621 **None** (@Anthonygansauer) · 2026-05-05 02:07

[[![digital chart](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/0/c04b95a267f06766fa63646e609cc948e0003a2a_2_690x552.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/0/c04b95a267f06766fa63646e609cc948e0003a2a_2_690x552.jpeg)

digital chart1000×800 776 KB](/uploads/short-url/rr7C1SaSHxAzl7wuXsUxpoksZcK.jpeg?dl=1)

[[![RA4 Chart](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/8/68895fe91605c8357a05ff0136e4bc9d91ddec53_2_690x552.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/8/68895fe91605c8357a05ff0136e4bc9d91ddec53_2_690x552.jpeg)

RA4 Chart1000×800 514 KB](/uploads/short-url/eULYO21bOiQtsm2lEBeCxiySgaT.jpeg?dl=1)

added a raw file + ra4 print of a color chart to my google drive for others to try to match it. Struggling to get the digital to match the print, maybe you all can try?

portra 400+ Fuji DPii

Lumix S5ii Raw

[https://drive.google.com/drive/u/0/folders/1ryifCcPHbDQoFiofn46u1Wiymi4RoxdE](https://drive.google.com/drive/u/0/folders/1ryifCcPHbDQoFiofn46u1Wiymi4RoxdE)

---

## #622 **** (@RoughDraftWriting) · 2026-05-05 04:45

This is beautiful! Did you just pull a hald image into spectra film? How did you manage to get the LUT output and working with Resolve? I’d love to make some spektrafilm LUTs that work with DWG/DWI.

---

## #623 **John A** (@John_A) · 2026-05-05 05:19

Is this simulation any different compared to Genesis?

---

## #624 **Ryan Cara** (@Ryan_Cara) · 2026-05-05 05:50

You can try this tool I posted last week and use a CST from DWG/intermediate to AP0/Linear.

<aside class="onebox githubrepo" data-onebox-src="https://github.com/ryancara/Spektrafilm-LUT-Generator">
 <header class="source">

 [github.com](https://github.com/ryancara/Spektrafilm-LUT-Generator)
 </header>

 <article class="onebox-body">




[![图片625](https://d2x313g9lpht1q.cloudfront.net/original/3X/2/9/29a0b4676637c17dd2e4d0782c924c6a7574c29c.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/2/9/29a0b4676637c17dd2e4d0782c924c6a7574c29c.png)


### [GitHub - ryancara/Spektrafilm-LUT-Generator: Generates a CLF or Cube LUT from Arctic's...](https://github.com/ryancara/Spektrafilm-LUT-Generator)


<span class="github-repo-description">Generates a CLF or Cube LUT from Arctic's Spektrafilm spectral film simulation app.</span>

 </article>









</aside>

Otherwise it was also pointed out that VKDT works very well for video. I tried it out this week and it looked great…especially with all of the spatial features in Spektral that you miss out on with a LUT.

---

## #625 **** (@janogarcia) · 2026-05-05 06:37

Awesome examples so far on matching analog prints and S5II RAWs.

[![:ok_hand:](https://discuss.pixls.us/images/emoji/apple/ok_hand.png?v=12)](https://discuss.pixls.us/images/emoji/apple/ok_hand.png?v=12)

[![:sparkles:](https://discuss.pixls.us/images/emoji/apple/sparkles.png?v=12)](https://discuss.pixls.us/images/emoji/apple/sparkles.png?v=12)

As for the equally awesome S5II in-camera Ektachrome LUT, any chance you could share it?

I don’t have an S5II/S5IIx *yet*, but I’d love to experiment with some RAW samples and maybe try to adapt it somehow for Magic Lantern RAW video (Canon 5D III) using Lattice.

---

## #626 **Mateusz Grabowski** (@Mateusz_Grabowski) · 2026-05-05 07:44

Yes I did just that. In srgb only though. I graded evrything in DWG and put the lut in the last node after color space transfortm to rec709/2.4. Works well enough!

---

## #627 **Mateusz Grabowski** (@Mateusz_Grabowski) · 2026-05-05 07:46

I will try it this weekend hopefully when I’ll have the time

[![:slightly_smiling_face:](https://discuss.pixls.us/images/emoji/apple/slightly_smiling_face.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slightly_smiling_face.png?v=12)

---

## #628 **Dissipatio ** (@Dissipatio) · 2026-05-05 07:59

Andrea, thanks.

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

Spectral is great.

I use DxO for optical corrections and AI pre-sharpening/Denoise, export to linear DNG, and then use Spectral.

---

## #629 **Mateusz Grabowski** (@Mateusz_Grabowski) · 2026-05-05 08:01

I found a nice and very simple program called PNG2Cube. Converts hald image to cube lut.

---

## #630 **jo** (@hanatos) · 2026-05-05 08:13

> **@arctic** (帖子 #559):
> hanatos:

does the middle grey spectrum fall off to zero? or is this about frequency domain over lambda more than uv and near-ir?

i am not sure about the extreme purple line, i am pretty sure it will suffer, but during the weekend i got some results from a sidequest: trying to optimize the bandpass filters for every stock. the results might give some insight on these questions (and there might be pitfalls). any feedback is very welcome of course!

</blockquote>
</aside>

hah, you’re moving too fast for me to keep up

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

here’s a plot of some green in the cc24 and saturated magenta:

[[![20260505_09h53m20s_grim](https://d2x313g9lpht1q.cloudfront.net/original/3X/a/9/a9ba287b0eabb806df557e4b03d6654270e42b32.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/a/9/a9ba287b0eabb806df557e4b03d6654270e42b32.png)

20260505_09h53m20s_grim565×715 74.7 KB](/uploads/short-url/odtx8rBxmDn6umgDL4RoLXfApHQ.png?dl=1)

due to the nature of the sigmoid spectra, they are based on a quadratic/parabola that either has a peak or a dip. anything in this rough triangle between blue, white, and red has a “dip” shape and will not fall off to zero at the rims.

the spectra are optimised to round trip/reproduce exactly the rgb values when integrated against the 1931 cmf and a D65 illuminant. if i understand correctly you are essentially trying to correct this to make the upsampling closer to the metameric space of the sensitivities of specific film stock, not the cmf of a human observer.

if this is indeed making a lot of visual difference, it opens a whole new rabbit hole… it’s probably better to optimise the spectral upsampling for each film stock’s sensitivities in this case (can get near perfect match then), and also it opens the question whether this should in fact take place as device input transform, i.e. work on raw camera rgb as input. this is already such an ill-posed problem (vkdt has some input device transform based on the spectral sensitivities of a camera, should you possess them). i’m a bit hesitant to add after-the-fact correction here, though spectral windowing makes sense.

what’s the analog correspondence to the window by the way? is there some ir/uv blocking layer in film stock or would that traditionally happen in the glass/coating? i mean, does it in the actual analog world depend on the film stock or is this really just a numerical post process of the data.

---

## #631 **Andrea** (@arctic) · 2026-05-05 11:58

> **@Anthonygansauer** (帖子 #605):
> heres a google drive so you guys can match and play with it yourself!

thank you so much, I’ll have some busy days ahead but I will play with them soon! amazing!

i especially wanna give a shot to the colorcheker photo, because i made some improvements to the sensitivity-adaptation model of the spectral upsampling in the weekend.

> **@Anthonygansauer** (帖子 #606):
> top is real film + RA4 print scaned

these are outstanding!!!

> **@Anthonygansauer** (帖子 #612):
> The great thing about Lumix S5 series is you can use 3Dluts for stills.

I did end up to buying a lumix S9 and experimenting with it, I actually bought the camera only for the 3dlut feature for still, and for the ability to shoot stills with the log video pipeline (VLog). the lumix video pipeline have such a nice texture in my opinion, not oversharpened and smoother noise than the still one. I’ll post some pics soon. here a couple of random SOOC that happened to be on my phone.

[[![P1000602](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/e/aeb783b5fb743c852a64eb98d4a937a7dbbc20f2_2_690x253.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/e/aeb783b5fb743c852a64eb98d4a937a7dbbc20f2_2_690x253.jpeg)

P10006026000×2208 3.17 MB](/uploads/short-url/oVCfZbfNYcgWEpD2XBKl3DWWQsG.jpeg?dl=1)

[[![P1000501](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/3/a36ad4b06b4b9889fd1ee930cc9f8342a55e516d_2_690x253.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/3/a36ad4b06b4b9889fd1ee930cc9f8342a55e516d_2_690x253.jpeg)

P10005016000×2208 4.58 MB](/uploads/short-url/njEI7AOfYnyrAj9pRpt3xedSc0t.jpeg?dl=1)

I lost track of the code experiment but i have the VLog LUT computation script somewhere, very WIP, and very rudimentary, but at least the lut can use the full dynamic range of the camera (12bit only for the Lumix s9 because panasonic is evil and just blocked the slow readout mode with higher snr, arrrr, no mechanical shutter in the camera i know, but… just evil).

> **@Mateusz_Grabowski** (帖子 #614):
> Here is a video I made yesterday using exported haldcluts from spektrafilm. With couplers included!

very juicy colors!

> **@sahuaro.senorita** (帖子 #616):
> “Installed 1 executable: spektrafilm”

if you use `uv install tool ...` you should be able to run the command `spektrafilm` from the terminal from anywhere

---

## #632 **** (@Thomsen) · 2026-05-05 12:58

> **@arctic** (帖子 #631):
> I actually bought the camera only for the 3dlut feature for still

Just to make sure - the Lumix cameras can’t do all the spectral stuff, right? Only lut for contrast/color?

---

## #633 **** (@Thomsen) · 2026-05-05 12:59

Magic Lantern, the hacked Canon OS came to mind. Imagine if you could do the whole Spectral simulation in-camera…

---

## #634 **Andrea** (@arctic) · 2026-05-05 13:06

> **@hanatos** (帖子 #630):
> if i understand correctly you are essentially trying to correct this to make the upsampling closer to the metameric space of the sensitivities of specific film stock, not the cmf of a human observer.

I am starting from real spectra of which i can compute the projection on the 1931 cmfs and the projections on the film sensitivities (ground truth). then i am computing XYZ with the real spectra and upsampling using your algorithm. i get a spectrum with zero error XYZ values when reprojected on the 1931 cmfs, but inevitably will give big errors on the film sensitivities.

the reason is exactly the nature of the sigmoid spectra that have uv/ir lobes if “dip” type. but can extend in near uv and near ir even if “peak” at the edges of the visible range.

here comes the idea of an optimized bandpassed upsampling that can reduce the round trip error with the real spectrum exposures.

> **@hanatos** (帖子 #630):
> i’m a bit hesitant to add after-the-fact correction here, though spectral windowing makes sense.

then i am very gulty! i tried to go past the optimal per channel bandpass in the weekend.

[![:stuck_out_tongue:](https://discuss.pixls.us/images/emoji/apple/stuck_out_tongue.png?v=12)](https://discuss.pixls.us/images/emoji/apple/stuck_out_tongue.png?v=12)

i would say it makes visual difference, and i think that it is very noticeable from no-bandpass to bandpass. and it can reach almost visual imperceptible difference (average max errors <2/20 ev for more half of the corpus, and <3/20 ev for 90+%). the correction adds a “simple” per channel parametric exposure correction map in the xy plane (tc coord.).

here an example with a colorchecker reflectance dataset using D55 illuminant, and projected on kodak_portra_400 sensitivities. the outer square are the real reflected spectra exposures (visualized as straight sRGB, so not the real colors, but it helps seeing the differences).

(left) uncorrected (`hanatos2025` spectra), (center) bandpassed, (right) band passed and per channel exposure correction.

[[![f4_colorchecker_kodak_portra_400 - Copy](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/2/12b976d65e8138f1b5c1577f1b9c7aa23dd441f2_2_690x183.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/2/12b976d65e8138f1b5c1577f1b9c7aa23dd441f2_2_690x183.png)

f4_colorchecker_kodak_portra_400 - Copy4770×1271 74.9 KB](/uploads/short-url/2FDWSEDpELuefuioOakQa3kXs42.png?dl=1)

the results are quite ok, even if it is a correction procedure, thus intrinsically not very elegant. i see it as a sensitivity-adaptation of the original algorithm. since sensitivities are not so different from cmfs, the adaptation can be encoded in 15-20 parameters per channel (parameters of the bandpass and of the 2d surface smooth function). the benefit is also that it seems we keep some of the good qualities of your underling sigmoid alg, ie it has a smooth solution across the xy plane.

here an example of a fitted 2d function on the xy plane. i am using saturating functions so it is arbitrarily bounded to the range of maximum correction we want allow.

[[![f5_topographic_kodak_portra_400](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/a/6ab2d7a01723faa3904bdd09e8c245025d7d074e_2_690x205.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/a/6ab2d7a01723faa3904bdd09e8c245025d7d074e_2_690x205.png)

f5_topographic_kodak_portra_4005063×1511 398 KB](/uploads/short-url/fdTMlabAskkT3cqp7B0Rx4189BA.png?dl=1)

here also some plots of log exposure errors of a few spectral dataset from `colour-science`. first column is just `hanatos2025` roundtrip error, center is just bandpass, and right is bandpass + surface correction.

[[![f2_pancake_kodak_portra_400](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/3/331f12fdc56592c9e80576e0196f07d203d292e5_2_690x552.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/3/331f12fdc56592c9e80576e0196f07d203d292e5_2_690x552.png)

f2_pancake_kodak_portra_4006000×4800 2.17 MB](/uploads/short-url/7ieVtSf2FnGA7uNptE4Lks7S9Bb.png?dl=1)

we cannot expect a perfect planar pancake because the metameric spaces are supposed to be slightly different. but we can compress it in a minimal sense.

overall the bandpass is shared, cheap and easy compute, and the three exposure corrections are also not expensive to compute. it is a dirty solution but seems to work ok-ish and does not require to ship a new lut of the sigmoid spectra in triangular coordinates for every stock. but it is still a correction and might not make people feel clean

[![:laughing:](https://discuss.pixls.us/images/emoji/apple/laughing.png?v=12)](https://discuss.pixls.us/images/emoji/apple/laughing.png?v=12)

working with RGB from raw files seems the logical portable standard, even if in the way above implies `camera sensitivity exposure -> rgb -> spectra -> sensitivity adaptation -> film sensitivity exposure`; but it stays agnostic of the camera sensitivity (we trust the manufacturers/calibrators that the rgb of raw files are good estimates).

anyway the error above are against real spectra so it shows that the procedure, although not elegant is compact in amount of parameters and kinda working in the real world.

> **@hanatos** (帖子 #630):
> what’s the analog correspondence to the window by the way?

in analog cameras, lenses have uv absorption and will gently band pass the near uv region, the near ir is more open. film might have also color filter but this is already an effect included in the sensitivities (that are still density measurment on the effective photo process after all).

but in this case the window takes care of the overshooting of the lobes of the sigmoid spectra compared to real ones, tha’s it. the “dip” simgoid spectra are a particular kind of metamers with huuuuuge non visible contribution (even xrays

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 ). the bandpass just tame those to mimic the average behavior of real spectra corpus. essentially we are injecting the trends of the corpus in the bandpass and 2D surface, hoping that the simple bandpass+surface model can generalize in a handfull of parameters the sensitivity-adaptation-trasnform of the upsampling algorithm (with low enough error).

if we wanted to optimize the sigmoid spectra in a camera sensitivity agnostic way (thus starting from RGB → XYZ), i guess the procedure would still end up relying on a spectral dataset to minimize the round trip error the upsampled spectra on film sensitivities while keeping an assigned XYZ to the orginal spectra. this because we would not have any ground truth for the film exposures.

but this is not my field and i might be taking huge assumptions that are wrong

[![:grin:](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)

---

## #635 **Yogansh Bhatt** (@Yogansh_Bhatt) · 2026-05-05 13:10

You might wanna have a look at Motioncam Pro on android if by any chance you own an android

[![:slightly_smiling_face:](https://discuss.pixls.us/images/emoji/apple/slightly_smiling_face.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slightly_smiling_face.png?v=12)

The mcraw is natively supported by vkdt but if you want your smartphone to spit out amazing images/videos then it might be interesting for you (it’s not foss so I don’t like to mention it on pixls but it started as one by a single dev so I feel tiny bit less guilty).

---

## #636 **Andrea** (@arctic) · 2026-05-05 13:11

they can do all that can be encoded in a VLog 3D lut, thus the result of the full spektrafilm computation for a fixed set of paramters, minus non-local and stochastic effects (halation, scatteing, grain, diffusion filters, diffusion of couplers, etc…). i would say it is like having the ART implementation in camera but only with fixed presets. white balance works fine i would say, because by design spektrafilm was designed to preserve 18% midgray input->ouptut.

---

## #637 **Yogansh Bhatt** (@Yogansh_Bhatt) · 2026-05-05 13:15

Ofcourse this was along the lines of what [@Thomsen](/u/thomsen) suggested . I even saw a very WIP port of filmsim and Spektrafilm but we shall see if the dev decides to finish it and publish it . (Should be foss that one ofcourse). I believe those Androids have benefited a lot from all these amazing projects… pretty much Magic Lantern territory.

---

## #638 **** (@yairs) · 2026-05-05 14:17

This looks really nice! mind sharing your json file of this one?

---

## #639 **** (@RoughDraftWriting) · 2026-05-05 14:36

Looks really interesting, unfortunately I haven’t been able to get your LUT generator or VKDT working properly on my mac. It’s probably user error

[![:sweat_smile:](https://discuss.pixls.us/images/emoji/apple/sweat_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/sweat_smile.png?v=12)

[[![Screenshot 2026-05-05 at 7.35.31 AM](https://d2x313g9lpht1q.cloudfront.net/original/3X/3/a/3af9479a5a989452e67b3939a72f214306e5424a.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/3/a/3af9479a5a989452e67b3939a72f214306e5424a.png)

Screenshot 2026-05-05 at 7.35.31 AM245×281 24.3 KB](/uploads/short-url/8pHLTMYiJh1LmRrGFYQDuB0or9g.png?dl=1)

I just get this message despite having the proper permissions, etc.

---

## #640 **None** (@sahuaro.senorita) · 2026-05-05 14:46

> **@arctic** (帖子 #631):
> if you use uv install tool ... you should be able to run the command spektrafilm from the terminal from anywhere

very sorry but i don’t know how to do this. i basically never use the terminal unless i have commands to paste into it.

---

## #642 **** (@mikae1) · 2026-05-05 20:23

> **@sahuaro.senorita** (帖子 #640):
> very sorry but i don’t know how to do this. i basically never use the terminal unless i have commands to paste into it.

To create a persistent installation:

```
uv tool install git+https://github.com/andreavolpato/spektrafilm.git@dev

```

To start it:

```
spektrafilm

```

To upgrade it:

```
uv tool upgrade spektrafilm

```

Just copy and paste those into your terminal.

---

## #643 **Ryan Cara** (@Ryan_Cara) · 2026-05-05 23:19

Try this in terminal:

> cd /path/to/your/downloaded/Spektrafilm-LUT-Generator
>
> chmod +x launch_mac.command

Then try run again

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

Alternatively

> conda activate spektrafilm
>
> python “/path/to/Spektrafilm-LUT-Generator-main/spektrafilm_state_to_lut_gui.py”

---

## #644 **None** (@sahuaro.senorita) · 2026-05-06 01:04

> **@mikae1** (帖子 #642):
> To start it:

```
spektrafilm

```

thank you so much! i can’t believe it was just that easy.

---

## #645 **** (@cometface589) · 2026-05-06 07:58

how do I export as a high resolution file? when I press the save button all I get are very low resolution files.

---

## #646 **Benjamin** (@piratenpanda) · 2026-05-06 09:27

did you press scan before to calculate the high resolution image?

---

## #647 **** (@mikae1) · 2026-05-06 11:03

> **@Ryan_Cara** (帖子 #619):
> Does the method I provided push things outside of the boundaries? If so, @slazaar, it might be worth going Darktable (Export Prophoto RGB Linear) → Photoshop → Spektrafilm.

That is the order of things I would recommend (if one needs to use Photoshop), yes.

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

---

## #648 **jo** (@hanatos) · 2026-05-06 11:20

> **@arctic** (帖子 #634):
> I am starting from real spectra of which i can compute the projection on the 1931 cmfs and the projections on the film sensitivities (ground truth). then i am computing XYZ with the real spectra and upsampling using your algorithm. i get a spectrum with zero error XYZ values when reprojected on the 1931 cmfs, but inevitably will give big errors on the film sensitivities.

okay, so far this works as expected

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

> **@arctic** (帖子 #634):
> the reason is exactly the nature of the sigmoid spectra that have uv/ir lobes if “dip” type. but can extend in near uv and near ir even if “peak” at the edges of the visible range.

no wait. the sensitivities are windowed, both the cmf and the film ones. so by windowing some more, you’re changing the ratio of r/g/b response (the window falls off really soft in the ir range).

fitting this extra error correction to some specific spectral shape seems arbitrary, but you’re using quite a relevant set of spectra here. and your plots with errors mostly in the dip-shape regions are kinda convincing. in the interest of reducing the amount of extra data/correction terms we have floating around here… would it make sense if i tried to introduce some fixed/static windowing and re-optimise the spectral lut with that in the loop? i’m assuming it wouldn’t change the behaviour of the xyz roundtrip much but would provide us with windowed spectral upsampling. this wouldn’t address metamer mismatch, but now i’m curious…

---

## #649 **** (@mikae1) · 2026-05-06 11:34

> **@sahuaro.senorita** (帖子 #644):
> mikae1:

To start it:

```
spektrafilm

```

thank you so much! i can’t believe it was just that easy.

</blockquote>
</aside>

It was said above, but it’s becoming a bit hard to follow the different discussions in this thread.

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

Perhaps Spektrafilm — and its implementations in ART and vkdt — soon deserves its own category, [@paperdigits](/u/paperdigits) and [@hanatos](/u/hanatos)? People who are not so close to development and Linux seem to be discovering Spektrafilm (which is great!) and a support thread, for solving installation issues and things like that, might be a good idea.

---

## #650 **** (@cometface589) · 2026-05-06 14:49

oh sweet I was totally missing that part. Is there a way to save it as 16 bit tif or is JPG the only option right now. when I try to save it I don’t see an option to save as tif only jpg. thanks for your help on the scanning part!

---

## #651 **Mica** (@paperdigits) · 2026-05-06 14:59

> **@mikae1** (帖子 #649):
> and its implementations in ART and vkdt — soon deserves its own category, @paperdigits and @hanatos?

Sure, if [@arctic](/u/arctic) would find it useful.

---

## #652 **** (@mikae1) · 2026-05-06 15:32

> **@cometface589** (帖子 #650):
> Is there a way to save it as 16 bit tif or is JPG the only option right now. when I try to save it I don’t see an option to save as tif only jpg.

The TIFF option is gone. If you want lossless, use PNG (8-bit only, I believe) or OpenEXR (more bits, probably).

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

---

## #653 **Georg N** (@geni1105) · 2026-05-06 16:19

That’s a great suggestion, thanks! I and probably many others would really appreciate a separate thread on installation issues.

For example, I am currently stuck when upgrading from agx-emulsion (working fine with python 3.11) to spektrafilm (apparently requiring python 3.13, but pip then complaining about

ERROR: Ignored the following versions that require a different python version: 0.4.0 Requires-Python >=3.8,<3.11; 0.4.1 Requires-Python >=3.8,<3.11; 0.4.2 Requires-Python >=3.9,<3.12; 0.4.3 Requires-Python >=3.9,<3.12; 0.4.4 Requires-Python >=3.9,<3.13; etc. etc.

Any hints? Thanks!

(MacOS 15.7)

---

## #654 **Mateusz Grabowski** (@Mateusz_Grabowski) · 2026-05-06 17:06

Ok this is the last video I will post here! (maybe someone should create separate topic dedicated to sharing work created with spektrafilm?)

 <iframe src="https://www.youtube.com/embed/TeI1RHc0Wd0?feature=oembed&wmode=opaque" width="480" height="360" frameborder="0" allowfullscreen="" class="youtube-onebox" seamless="seamless" sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox allow-presentation"></iframe>

Lumix S5IIX in V-Log with TTartisan 35mm f1.4. (APS-C Lenses on Full-Frame cameras have some interesting advantages!)

Portra 800 with Fuji Crystal Archive Paper.

Exposure, Contrast and minor saturation and hue tweaks done in DWG colorspace. LUT applied after conversion to rec709/2.4.

Happy Spring Everyone!

---

## #655 **** (@mino) · 2026-05-06 17:50

Beautiful, especially the opening shot. I this would make a great first post for that spektrafilm showcase thread

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 !

---

## #656 **** (@europlatus) · 2026-05-06 17:57

> **@priort** (帖子 #578):
> Ya I will have to check I run a pretty standard 120 cd/m2

FYI, I just did a calibration on my monitor, and the brightness was reduced, so I obviously had my monitor brightness set a bit too high. Taking a look at that photo again, it definitely seems quite dark. Given the lighting conditions, I feel like the white of the railing should be bright white and close to the white of the photo border, but it’s noticeably darker. However, I can still see all of the faces, and the style is obviously designed to be high contrast but with lower dynamic range, in the style of old film.

The guy with the blue jeans to the right of the front guy in white has only half of his face visible, but none of them are totally obscured.

My suspicion is that most people have their monitors set brighter than a calibrated monitor. It’s like when you set your TV to movie mode, and it’s suddenly dark, warm and muted. It’s designed to accurately show what the director intended, but it’s not what people are used to if they watch regular TV broadcasts.

---

## #657 **Todd Prior** (@priort) · 2026-05-06 18:54

It will be nice if, what is it called “perceptual quantitizer” transfer curves became more widespread… I dont’ fully understand it but once you have bright, higher bit displays I think these curves use absolute values can replace sdr gamma, so that when you move to a different monitor…even a much brighter one set to some other default level that your image will show diffuse white at whatever it was defined at on your device?? I think ?? **SMPTE ST 2084**

But here for sure its a high contrast image with deep blacks so its going to likely look different between users with substantially different peak brightness level on SDR monitors… My Acer also has a thing called black boost which I think is a sort of BP compensation the will lighten and provide more detail in the shadows but I have it turned off…others might have things like that enabled further changing the perception of the render… There is no doubt about the colors and atmosphere that you can achieve with these film sims…I feel bad as I haven’t really had time to explore them in any great detail…

---

## #658 **** (@mikae1) · 2026-05-06 20:24

> **@geni1105** (帖子 #653):
> I and probably many others would really appreciate a separate thread on installation issues.

The New Topic button is right at the top of first page of the forum and [I pressed it](https://discuss.pixls.us/t/spektrafilm-troubleshooting-installing-upgrading-etc/57453).

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

---

## #659 **Tim** (@Soupy) · 2026-05-06 23:46

The module should be called “I can’t believe it’s not film!”

---

## #660 **Upperechelonstr8up** (@upperechelonstr8up) · 2026-05-07 06:30

Does using an LUT like this produce a different result than exporting each frame in spektrafilm by hand/a script

---

## #661 **Mateusz Grabowski** (@Mateusz_Grabowski) · 2026-05-07 08:11

I don’t know about color but you definitely loose grain, halation etc.

---

## #662 **John A** (@John_A) · 2026-05-07 11:31

Is MTF built in or does it have to be additionally added?

---

## #663 **Ryan Cara** (@Ryan_Cara) · 2026-05-07 14:29

As mentioned, you do lose grain and halation. But there are also some spatial features that you miss out on that will affect the colour slightly! If your goal is to use this for video, the most faithful implementation is currently VKDT

[![:innocent:](https://discuss.pixls.us/images/emoji/apple/innocent.png?v=12)](https://discuss.pixls.us/images/emoji/apple/innocent.png?v=12)

That being said, using a LUT can still look excellent!

---

## #664 **Gonçalo** (@ggoncalo) · 2026-05-07 15:08

Hi everyone! First time posting here.

I came across SpektraFilm yesterday through a Reddit post, and I was really impressed by the results and the level of detail and research that went into the project. I have no doubt this is going to be a game changer for film simulation, so I went ahead and installed it on my Mac.

I’ve been tweaking some settings, but there are a few things I’d like to ask to make sure I’m taking full advantage of the software:

1. What’s the recommended workflow?
 Basic RAW editing in software like Darktable/Lightroom/C1 → SpektraFilm → Photoshop (if needed)? Or do you recommend opening the RAW file directly in SpektraFilm? And if you do use another editor beforehand, do you export in the ProPhoto color space?
2. This is probably a dumb mistake on my part, but I can only seem to export low-resolution JPEGs by hitting “Save.” I’m not managing to export a lossless file. What am I missing? Is lossless export only possible through the command line?

---

## #665 **Todd Prior** (@priort) · 2026-05-07 15:31

[@Soupy](/u/soupy) I couldn’t resist…

> **@Soupy** (帖子 #659):
> The module should be called “I can’t believe it’s not film!”

 <iframe src="https://www.youtube.com/embed/mqtsgH_wnn4?feature=oembed&wmode=opaque" width="480" height="360" frameborder="0" allowfullscreen="" class="youtube-onebox" seamless="seamless" sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox allow-presentation"></iframe>

---

## #666 **Gonçalo** (@ggoncalo) · 2026-05-07 17:07

This is crazy. Two questions: are you doing the matching between film and digital by eye comparison or are you using some script? Also, is that 3D LUT feature only applicable to JPEGS or is that present in the RAW files too?

---

## #667 **Steven** (@123sg) · 2026-05-07 17:15

> **@ggoncalo** (帖子 #664):
> but I can only seem to export low-resolution JPEGs by hitting “Save.” I’m not managing to export a lossless file. What am I missing?

I’m very much learning myself, but you need to hit the “SCAN” button, after finishing tweaking (as it’s relatively slow) before doing save as you are.

Took me a minute to realise too

[![:wink:](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)

> **@ggoncalo** (帖子 #664):
> Basic RAW editing in software like Darktable/Lightroom/C1 → SpektraFilm → Photoshop

To my understanding, to get the full benefit of the accurate simulation the input needs to be a linear file, so no tone curve applied - in darktable just turn off the tonemapper (Sigmoid/AgX/filmic) but not sure how that works in other software.

---

## #668 **** (@Cristian) · 2026-05-07 17:22

1. I open the raw file directly in spektrafilm, this saves me the trouble to open the raw in another software and also save me hdd space.
2. After you make the adjustments click scan and then save jpeg at full resolution. This project is under development so it will take a while to scan.
3. Happy editing
 [![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

---

## #669 **Gonçalo** (@ggoncalo) · 2026-05-07 17:28

Thanks a lot Cristian!

---

## #670 **Gonçalo** (@ggoncalo) · 2026-05-07 17:29

Thanks a lot Steven!

---

## #671 **None** (@Anthonygansauer) · 2026-05-07 17:37

I did the RA4 print first. Scanned it and match the digital within the program using its virtual enlarger settings. I saved it as a preset so I can use it every time, still a WIP tho, it’s not 100% accurate maybe around 70% accurate, still exploring some of the more complex coupler settings.

---

## #672 **Andrea** (@arctic) · 2026-05-07 18:13

> **@hanatos** (帖子 #648):
> fitting this extra error correction to some specific spectral shape seems arbitrary

i partially agree with this, and here is another comment on the problem. upsampling from XYZ inevitably cancel out all the information past the 1931 cmfs. if a real measured spectrum differs from another one in a range where the 1931 cmfs are zero, that information is inevitably lost, because the upsampler will return the same exact spectrum. thus if we want to reduce the roundtrip error of film exposures of real spectra we need to find that prior information somewhere else, and embed it somehow in the upsampling alg.

we just need to hope that typical natural reflectance spectra behave smoothly enough for a few tens of nanometers past the 1931 cmfs (film sensitivities are not that wider) so the information compresses well. if we are confident on the corpus quality and completeness than bandpass+surface is just a way to fit that information in a handful of parameters. the upsampling+bandbass+surface is more like a black-box for XYZ → reasonable RGB film exposures (reasonable as in minimal error given the few parameters).

the upsampling provides a cmfs-zero-error-base for the visible central part, bandpass+surface encodes the exposure morphing on the xy landscape of the prior information that reduces the roundtrip error. (haven’t tried, but i am pretty sure that given a fixed upsampling alg, the bandpass can be encoded as a surface log exposure correction on a set of film sensitivities, mmmm, i will think more on that lead).

> **@hanatos** (帖子 #648):
> would it make sense if i tried to introduce some fixed/static windowing and re-optimise the spectral lut with that in the loop? i’m assuming it wouldn’t change the behaviour of the xyz roundtrip much but would provide us with windowed spectral upsampling. this wouldn’t address metamer mismatch, but now i’m curious…

i think that adding a smooth bandpass window and reoptimize the the upsampling alg is a great idea! i believe it will give a much better metameric base for the film sensitivities, that will behave much better, especially for the spectra peaking at the blue/red or with side lobes. so less error from the start on film sensitivities whatever we decide to do after.

what window? and how much does it matter the particular shape? good questions.

here a couple of provocatory experiments to give “food for thought”.

i tried a square bandpass with edges at 1 percentile of blue and red LMS sensitivities. in this case we are cutting the upsampled spectra and keeping essentially zero error on the 1931 cmfs. then i fitted a poly surface log exposure correction.

[[![f3_ecdf_kodak_portra_400](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/9/99973e23eee3870d744cf03e54b0b02c22d793de_2_300x250.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/9/99973e23eee3870d744cf03e54b0b02c22d793de_2_300x250.png)

f3_ecdf_kodak_portra_4002107×1658 186 KB](/uploads/short-url/lUJ5wi5lc8wW7xHks9BQ68NXFz8.png?dl=1)

[[![f2_pancake_kodak_portra_400](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/7/476000f1ad263c503adc2d93dafbeb0b2af52075_2_300x250.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/7/476000f1ad263c503adc2d93dafbeb0b2af52075_2_300x250.png)

f2_pancake_kodak_portra_4006000×4800 2 MB](/uploads/short-url/abpApMW5xKKjdA8ryZGDi66inBj.png?dl=1)

similarly we can use a smooth logistic window shape that have flex points at the same percentile edges. in this case we can fit window and surface at the same time.

[[![f3_ecdf_kodak_portra_400](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/1/51794a241cdd1414310e655eba3a45297bbdfdff_2_300x250.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/1/51794a241cdd1414310e655eba3a45297bbdfdff_2_300x250.png)

f3_ecdf_kodak_portra_4002107×1658 186 KB](/uploads/short-url/bCKxhRtibcmhZFeGSBNIAUABYVF.png?dl=1)

[[![f2_pancake_kodak_portra_400](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/0/9036deb399604674110d3c9f31e2101ccdc746b6_2_300x250.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/0/9036deb399604674110d3c9f31e2101ccdc746b6_2_300x250.png)

f2_pancake_kodak_portra_4006000×4800 1.98 MB](/uploads/short-url/kzMjt6vFeYPWKgKzc3iV8mvHi0m.png?dl=1)

with a smooth window, essentially, we are removing some of the correction duties from the surface. the smooth logistic window is morphing the upsampled spectra in the wavelength domain where we know as prior information that side lobes are bad for film sensitivities, thus it is a great space to act on.

,
[[![f3b_train_val_test_kodak_portra_400](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/8/0853bf4f1617d1ade00ebd8caa2f38c4a5e8ceed_2_300x250.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/8/0853bf4f1617d1ade00ebd8caa2f38c4a5e8ceed_2_300x250.png)

f3b_train_val_test_kodak_portra_4002425×1658 250 KB](/uploads/short-url/1bFfluIptsD3AH7hq8my94yvT0F.png?dl=1)

[[![f3b_train_val_test_kodak_portra_400](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/6/e6d2ee1a5063e7c41f8b19e747477028e835b3ae_2_300x250.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/6/e6d2ee1a5063e7c41f8b19e747477028e835b3ae_2_300x250.png)

f3b_train_val_test_kodak_portra_4002468×1658 245 KB](/uploads/short-url/wVXJuRnveMHQngzm1Y03FyMiaPY.png?dl=1)

the window do not have a big impact on most roundtrip errors (the loss is a bit lower for the smooth window), but it seems to help to give more capability to the same minimal surface model (11 params per channel in this case) that can generalize better for skin for example (skin are the most difficult spectra if training only on otsu+munsell).

we can have even sligthly better results by letting the window cut more in the visible range. i can try to reoptimize just window (no surface) for a few film stocks and try to see if there is a good average one. do you have a favorite sigmoid shape that you think is sound for spectral containment?

[update] early morning though: what if the window for your optimization would be somewhat shaped after D55 (the typical target of daylight film). let’s say a smooth version of D55 or a more aggressive windowed version with the central part resembling D55. wouldn’t it be a good choice also for the optimization? crazy idea? the though is coming after seeing the smooth shapes of optimized windows using better tail-chasing regularizers.

also would it make sense to have a D55 referenced upsampling for spectral film applications?

just an example: (still heavily dependent on sigmoid shape and optimization hyperparameters that i will tune)

[[![f1_anatomy_kodak_portra_400](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/b/abe87028d201e13cdea844ed1f9b2b4aa1a33cb0_2_300x400.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/b/abe87028d201e13cdea844ed1f9b2b4aa1a33cb0_2_300x400.png)

f1_anatomy_kodak_portra_4002371×2955 465 KB](/uploads/short-url/owLDUSjhWuD3kdrgAAr7WPbsZCo.png?dl=1)

[[![f3_ecdf_kodak_portra_400](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/c/fc91d99dc32b488f6ea080d977e100faab7162b2_2_300x250.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/c/fc91d99dc32b488f6ea080d977e100faab7162b2_2_300x250.png)

f3_ecdf_kodak_portra_4002107×1658 154 KB](/uploads/short-url/A2kNTVN8qXDTVkcNCrnSThHqnMS.png?dl=1)

---

## #673 **Andrea** (@arctic) · 2026-05-07 18:24

> **@paperdigits** (帖子 #651):
> Sure, if @arctic would find it useful.

good initiative, thank you.

i should start also a thread for the nerdy color discussions.

[![:grin:](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)

---

## #674 **Andrea** (@arctic) · 2026-05-07 18:28

there minimal implantation is in `main`, but currently i haven’t committed the fine tuning based on the mtf of portra 400, so the mtf might not be as realistic. i will commit it soon.

---

## #675 **Andrea** (@arctic) · 2026-05-07 18:29

> **@Mateusz_Grabowski** (帖子 #654):
> Ok this is the last video

this is beautiful! it shouldn’t be the last

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

happy spring too!

---

## #676 **Mica** (@paperdigits) · 2026-05-08 16:47

> **@arctic** (帖子 #673):
> good initiative, thank you.
i should start also a thread for the nerdy color discussions.

I am pretty dense. Is that a “yes” to a category? It’d be Software > Spektrafilm

---

## #677 **Andrea** (@arctic) · 2026-05-08 17:14

i confused the tag that appeared to the post for a category. i actually think the tag would do for now.

let’s let the project mature a bit and see as we go. thank you for being clear (and thank you also for all the help supporting the forum by the way, it is always good to remind it).

---

## #678 **jo** (@hanatos) · 2026-05-08 17:56

> **@arctic** (帖子 #677):
> i confused the tag that appeared to the post for a category. i actually think the tag would do for now.

i think you’re too modest

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 but actually maybe we should separate out a couple of the more recent colour/techy things into their own topic, category or not?

---

## #679 **Andrea** (@arctic) · 2026-05-08 18:16

sounds good!

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 here can be the home for [spektrafilm tech discussions](https://discuss.pixls.us/t/spektrafilm-tech-discussions/57512)

---

## #680 **Revanza Pratamasyah** (@Revanza_Pratamasyah) · 2026-05-08 21:56

Hi Mateusz

I would like to learn your step by step method of getting the LUT from SpektraFilm. Could you share the step by step details of it?

Thank you in advance!

---

## #681 **Vicer Fx** (@Vicer_Fx) · 2026-05-10 01:13

Hey I’m kinda of a noob when it comes to installing things via terminal, if it won’t take too much of your time could you create a little video demonstrating the process in conda?

---

## #682 **Gonçalo** (@ggoncalo) · 2026-05-10 01:45

[[![Captura de ecrã 2026-05-10, às 02.40.01](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/2/a233dc631c451fca76cf278aaa5c5b2dfcea6215_2_690x459.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/2/a233dc631c451fca76cf278aaa5c5b2dfcea6215_2_690x459.png)

Captura de ecrã 2026-05-10, às 02.40.011654×1102 2.9 MB](/uploads/short-url/n8UsCArzqu62Uf0yZSmuf10f5fT.png?dl=1)

[[![Captura de ecrã 2026-05-10, às 02.39.44](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/f/4fca65d858afa415c67959ee5fd3e59f38c161cb_2_690x461.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/f/4fca65d858afa415c67959ee5fd3e59f38c161cb_2_690x461.png)

Captura de ecrã 2026-05-10, às 02.39.442130×1424 5.88 MB](/uploads/short-url/bnRm2CK2RzuW5v6OUlkZ1Gbsq4r.png?dl=1)

Hi everyone!

Is anyone dealing with a decrease in saturation when exporting? These are both screenshots for the sake of storage here, but I think it’s visible. The top one is the image in spektrafilm, the bottom one is the export. My output/saving color space are both sRGB.

---

## #683 **Todd Prior** (@priort) · 2026-05-10 02:30

Be sure you try to evaluate the image with the hqp enabled…ie the high quality preview and then when you export set hqr …reprocessing to yes… This should make for a good match and finally maybe check what your display profile is set at and using…That is the profile that controls how your preview looks on the monitor…

---

## #684 **WG** (@BPH3647) · 2026-05-10 03:50

Theres been a persistent colorspace embedding issue on my end, maybe you share the same. Just assign a sRGB colorspace and the colors should pop back.

---

## #685 **Gonçalo** (@ggoncalo) · 2026-05-10 15:12

Sorry, where would you enable hqp? I only have a “Preview” option. When it comes to exporting, once I click “Save” that’s it, there are no reprocessing to choose or other exporting options. Weird.

As far as other settings, my input color space is set to ProPhoto RGB and output/saving color space is sRGB. I have tried this with “Scan for print” enabled and disabled but it happens anyway.

---

## #686 **Todd Prior** (@priort) · 2026-05-10 15:38

I’m on my phone and can’t do a screen shot. It’s in the lower ribbon bar hover over the icons…I think it’s next to Raw overexposure. It uses full image data so it’s the most accurate but also slower…

---

## #687 **Gonçalo** (@ggoncalo) · 2026-05-10 15:52

[[![Captura de ecrã 2026-05-10, às 16.46.40](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/b/5ba4a1a973bb6d396df36e0c5b290328c39fa4f6_2_690x106.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/b/5ba4a1a973bb6d396df36e0c5b290328c39fa4f6_2_690x106.png)

Captura de ecrã 2026-05-10, às 16.46.402868×444 221 KB](/uploads/short-url/d4IaBV92zl97OJ6PpbsTT82duzc.png?dl=1)

I can’t find that option. It’s as if I have a different version of the app, but I’m sure it’s the most recent one.

---

## #688 **Mica** (@paperdigits) · 2026-05-10 16:15

> **@priort** (帖子 #686):
> I’m on my phone and can’t do a screen shot. It’s in the lower ribbon bar hover over the icons…I think it’s next to Raw overexposure. It uses full image data so it’s the most accurate but also slower

This is about spektrafilm, not darktable. I don’t think there is a high quality option in spektrafilm.

---

## #689 **Gonçalo** (@ggoncalo) · 2026-05-10 16:25

This would explain the confusion, although my problem doesn’t have to do with image quality, but with color shifts in the exported file. Doesn’t seem like the majority are dealing with this so I wonder what am I doing wrong.

---

## #690 **Andrea** (@arctic) · 2026-05-10 16:35

i think it is a problem of display profile and monitor calibration. `napari` that currently run the image viewer in the simple spektrafilm gui is not color managed. so it is a bit hacky.

are you on windows? if yes, have you tried to click and unclick the button “use display transform” under the CONFIG tab? if the display transform is retrieved it will be signaled in the status bar. that works only in windows unfortunately for now.

without display transform you rely on the “output color space” in the MAIN tab, by setting it to something that somehow matches your display calibration. maybe you have an sRGB profile or settings in your os? in that case sRGB output might improve the situation.

---

## #691 **Georg N** (@geni1105) · 2026-05-10 18:21

What is your monitor color space? If it is wider than sRGB, the image will appear oversaturated if you set the output color space to sRGB.

---

## #692 **Todd Prior** (@priort) · 2026-05-10 18:41

Ya sorry I thought dark table was in the workflow…

---

## #693 **Gonçalo** (@ggoncalo) · 2026-05-11 03:58

Now I get it! I’m using a Mac and the screen gamut is Display P3, which is wider than sRGB. I wasn’t familiar with napari, but if it’s not color managed then it’s explained. Fingers crossed for a ICC-aware display management in the works.

Anyway [@arctic](/u/arctic) congratulations for what you’ve built here and for taking the time to help out.

---

## #694 **Andrea** (@arctic) · 2026-05-11 05:25

thanks!

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 you should try to set the output color space to Display P3, if i remember well it was added long time ago exactly to have a better color reproduction on mac.

---

## #695 **Georg N** (@geni1105) · 2026-05-11 09:08

Exactly, that‘s what I did on my iMac with DisplayP3 gamut.

Congratulations and big thanks for your great work!

---

## #696 **Andrea** (@arctic) · 2026-05-11 18:39

> **@mikae1** (帖子 #652):
> The TIFF option is gone

> **@cometface589** (帖子 #650):
> Is there a way to save it as 16 bit tif

16 bit TIFF is back

> **@mikae1** (帖子 #652):
> OpenEXR (more bits, probably).

exr is 16 bit by default

---

## #697 **Mateusz Grabowski** (@Mateusz_Grabowski) · 2026-05-11 19:28

1. Download or create Hald CLUT Identity.
 Since I have ImageMagick, I created mine using a command:
 “convert hald:12 -depth 16 -colorspace sRGB hald12_16bit.tif”
 You can also download this one:
 [File:Hald CLUT Identity 12.png - RawPedia](https://rawpedia.rawtherapee.com/index.php?title=File:Hald_CLUT_Identity_12.png)
 2.Import Hald CLUT into spektrafilm
2. In the Input tab select input color space to srgb and check the “apply cctf decoding” ON
3. In exposure tab I uncheck both auto exposure and auto compensation.
 camera compensation ev is set to 0 and print exposure is set to 1
4. Turn halation, grain, preflash and diffusion off
5. I leave couplers on but it is important to set diffusion size um to 0
6. In the scanner tab set unsharp mask and blur to 0
7. Press scan and save as .png
8. Using PNG2Cube program convert Hald CLUT file into .cube file. Program is very simple to use and instructions are

<aside class="onebox allowlistedgeneric" data-onebox-src="https://picturefx.itch.io/png2cube-converter-for-linux-and-windows">
 <header class="source">


[![图片671](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/9/c9ef2b6d427684a3bfd30216c351bd57e600e505.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/9/c9ef2b6d427684a3bfd30216c351bd57e600e505.png)

 [itch.io](https://picturefx.itch.io/png2cube-converter-for-linux-and-windows)
 </header>

 <article class="onebox-body">


[![图片672](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/d/2d32f92481bc18e3ae20b699478a4e92bbdf4d72_2_690x690.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/d/2d32f92481bc18e3ae20b699478a4e92bbdf4d72_2_690x690.png)

### [PNG2Cube Converter for Linux and Windows by PictureFX](https://picturefx.itch.io/png2cube-converter-for-linux-and-windows)

 </article>









</aside>

<ol start="10">
<li>Use these luts after converting your footage to rec709/gamma 2.4.</li>
</ol>

I created a “preset” with the exact settings I use for my luts:

<aside class="onebox googledrive" data-onebox-src="https://drive.google.com/file/d/1gYLJefcqmVg0Kul8S5ZlNQJcrpa4kAkx/view?usp=sharing">
 <header class="source">

 [drive.google.com](https://drive.google.com/file/d/1gYLJefcqmVg0Kul8S5ZlNQJcrpa4kAkx/view?usp=sharing)
 </header>

 <article class="onebox-body">
 [](https://drive.google.com/file/d/1gYLJefcqmVg0Kul8S5ZlNQJcrpa4kAkx/view?usp=sharing)

### [LUT-CREATION.json](https://drive.google.com/file/d/1gYLJefcqmVg0Kul8S5ZlNQJcrpa4kAkx/view?usp=sharing)

Google Drive file.

 </article>









</aside>

You can use “load from file” in spektrafilm to apply the settings.

One thing I cannot grasp is the size of the .cube files generated by PNG2Cube. Each lut is over 50mb which should not happen! I suspect that resolution of Hald image is too big. Hovewer re-exporting the lut with Davinci Resolve as 65-point cube creates appropriate file size

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

It is a miracle that I have managed to make this work because I have no idea what I am doing with all of this most of the time!

It works nicely for now but I really hope that [@arctic](/u/arctic) will implement dedicated lut export menu with options for print-only and film-only luts in the future!

---

## #698 **Vicer Fx** (@Vicer_Fx) · 2026-05-11 21:52

thanks a lot

---

## #699 **Revanza Pratamasyah** (@Revanza_Pratamasyah) · 2026-05-12 04:25

Thank you so much for the in depth guide Mateusz!!!

---

## #700 **Andrea** (@arctic) · 2026-05-12 04:46

> **@Mateusz_Grabowski** (帖子 #697):
> It works nicely for now but I really hope that @arctic will implement dedicated lut export menu with options for print-only and film-only luts in the future!

working on a nice solution for this

[![:+1:](https://discuss.pixls.us/images/emoji/apple/+1.png?v=12)](https://discuss.pixls.us/images/emoji/apple/+1.png?v=12)

---

## #701 **Vesnic** (@Vesnic) · 2026-05-12 13:07

This is absolutely brilliant, amazing beautiful and gorgeous. All the good tidings!

I know maybe you got this question a lot, but is there any, tiny, possibility one could actually turn this into an OFX plugin for Resolve?

I am a person with 0 skills in coding, but knowing about vibe coding, I am a bit tempted to go in murky waters and see if I can port it.

Thank you for any reply!

---

## #702 **Ryan Cara** (@Ryan_Cara) · 2026-05-12 14:24

It’s definitely possible. But with how much and quickly things are changing and being updated, I can’t imagine that it’d be a priority for now

[![:person_shrugging:](https://discuss.pixls.us/images/emoji/apple/person_shrugging.png?v=12)](https://discuss.pixls.us/images/emoji/apple/person_shrugging.png?v=12)

Having LUT export options for print and film separately will allow certain effects to be placed in-between, which will be great for Resolve users! Exciting

[![:innocent:](https://discuss.pixls.us/images/emoji/apple/innocent.png?v=12)](https://discuss.pixls.us/images/emoji/apple/innocent.png?v=12)

---

## #703 **Vesnic** (@Vesnic) · 2026-05-12 14:30

this is would be amazing! seriously. I am sure [@arctic](/u/arctic) knows one of the “best plugins” out there called Genesis, runs at around 2000$ a pop, and it is not as good as this. :)) of course im not talking anything but just about the irony of it

---

## #704 **WG** (@BPH3647) · 2026-05-12 14:45

> **@arctic** (帖子 #696):
> 16 bit TIFF is back

TYSM!

---

## #705 **Mateusz Grabowski** (@Mateusz_Grabowski) · 2026-05-12 16:26

> **@Ryan_Cara** (帖子 #702):
> Having LUT export options for print and film separately will allow certain effects to be placed in-between, which will be great for Resolve users! Exciting

And I also cannot wait to use the print luts on my film scans! Not sure how will I actually do it but maybe the new “photo” page in Resolve 21 will come in handy

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

Exciting indeed!

---

## #706 **Mateusz Grabowski** (@Mateusz_Grabowski) · 2026-05-12 16:52

Yesterday evening walk:

Lumix S5IIX, V-Log Open Gate, TTartisan 35mm f1.4, 5000K WB, Ultramax 400 on Fuji Crystal Archive

 <iframe src="https://www.youtube.com/embed/xIflnwhb2HA?feature=oembed&wmode=opaque" width="480" height="360" frameborder="0" allowfullscreen="" class="youtube-onebox" seamless="seamless" sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox allow-presentation"></iframe>

The light was basically perfect! Only adjusted exposure. No contrast or saturation changes.

I am amazed how easy it is now to get the look I want after years of learning and trying.

Thank you [@arctic](/u/arctic) !

---

## #707 **Andrea** (@arctic) · 2026-05-12 18:37

> **@Ryan_Cara** (帖子 #702):
> But with how much and quickly things are changing and being updated

yeah, things are far from finished (for example there are some exciting discussions in the tech thread for the next big steps in accuracy of the filming stage; i hope it will help getting closer matches with the samples by [@Anthonygansauer](/u/anthonygansauer)). anyway things are evolving quite fast.

i am very excited for this project (if it was not clear enough

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 ), and I am trying to balance sleep and day-work without burning out.

there are several milestone and ideas in the to do list. LUT export is of course a big priority, and will enable easy integration in other programs (without the non local-local and stochastic effects ofc). and LUTs are flexible for now and can easily be re-exported if big changes happen. plus i have a Lumix camera so i am even more driven in creating nice new LUTs for it!

> **@Mateusz_Grabowski** (帖子 #705):
> And I also cannot wait to use the print luts on my film scans!

i will explore reversing negative scans within the same spectral framework, it is not as simple as applying a print lut, but i have a clear blueprint in mind to try. and i am sure it is gonna be a fun little challenge to get right!

> **@Vesnic** (帖子 #703):
> this is would be amazing! seriously. I am sure @arctic knows one of the “best plugins” out there called Genesis, runs at around 2000$

i am aware of the landscape of plugins available, and i am sure they are already including (or-coming-soon-with) physically based spectral pipelines. they have totally different amount of money and resources, and many developers to deploy on features. so it will never be a fair race unfortunately.

but the beauty of the open-source/open-science is the possibility of collaborating with so many nice and competent people.

so just a reminder, this project is not free as in “free-beer”

[![:wink:](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)

 but open-source, and would not be possible without the help and support of many people here on pixls. so remember to thank everyone here contributing to this nice environment, and [@hanatos](/u/hanatos) in particular for the accuracy of the filming stage that is one of the big reasons the output is so good.

> **@Mateusz_Grabowski** (帖子 #706):
> The light was basically perfect!

stunning!!!

---

## #708 **Mateusz Grabowski** (@Mateusz_Grabowski) · 2026-05-12 19:46

> **@arctic** (帖子 #707):
> i will explore reversing negative scans within the same spectral framework, it is not as simple as applying a print lut, but i have a clear blueprint in mind to try. and i am sure it is gonna be a fun little challenge to get right!

Oh sweet! My idea was to just edit inverted scans “under” the print only LUT, the same way I do it with video for now

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

But the ability to work on it within spektrafilm engine sounds exciting!

I will happily re-scan and share some of my negatives to test that feature in the future if needed

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

---

## #709 **** (@RoughDraftWriting) · 2026-05-13 03:45

Even following all of these steps I keep ending up with broken LUTs

[![:sweat:](https://discuss.pixls.us/images/emoji/apple/sweat.png?v=12)](https://discuss.pixls.us/images/emoji/apple/sweat.png?v=12)

[[![Still 2026-05-12 204432_1.13.1](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/1/71c4b7b0b629d94256e6a650dbba359e0a0b6dff_2_690x388.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/1/71c4b7b0b629d94256e6a650dbba359e0a0b6dff_2_690x388.jpeg)

Still 2026-05-12 204432_1.13.13840×2160 4.57 MB](/uploads/short-url/gerq0JJHl3pED4b71oSsiPGrOX5.jpeg?dl=1)

---

## #710 **** (@RoughDraftWriting) · 2026-05-13 03:46

Just incredible!

---

## #711 **Ryan Cara** (@Ryan_Cara) · 2026-05-13 04:54

I really think that using a CUBE made for Rec709/sRGB is not going to look ideal, as Spektrafilm is really designed to work scene-linear input. I’d imagine it’d work okay in some situations and then break apart in others.

I would try out the tool I posted earlier (Which is based off ART’s implementation and takes Ap0/Linear in and out):

<aside class="onebox githubrepo" data-onebox-src="https://github.com/ryancara/Spektrafilm-LUT-Generator">
 <header class="source">

 [github.com](https://github.com/ryancara/Spektrafilm-LUT-Generator)
 </header>

 <article class="onebox-body">




[![图片684](https://d2x313g9lpht1q.cloudfront.net/original/3X/2/9/29a0b4676637c17dd2e4d0782c924c6a7574c29c.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/2/9/29a0b4676637c17dd2e4d0782c924c6a7574c29c.png)


### [GitHub - ryancara/Spektrafilm-LUT-Generator: Generates a CLF or Cube LUT from Arctic's...](https://github.com/ryancara/Spektrafilm-LUT-Generator)


<span class="github-repo-description">Generates a CLF or Cube LUT from Arctic's Spektrafilm spectral film simulation app.</span>

 </article>









</aside>

I can help you get it working over a DM if you’re unable!

Otherwise wait for Arctic’s official solution

[![:blush:](https://discuss.pixls.us/images/emoji/apple/blush.png?v=12)](https://discuss.pixls.us/images/emoji/apple/blush.png?v=12)

---

## #712 **Vesnic** (@Vesnic) · 2026-05-13 05:44

well the problem here is very common, the tints you get on highlights could even be related to restoring highlights. If you restore highlights in Resolve, sometimes it does that. Since you probably did it in a video editing software or Lightroom at most, try not to check the Restore Highlights box

---

## #713 **Vesnic** (@Vesnic) · 2026-05-13 05:48

with yout method i have seen this is what gets ignored:

- grain
- halation
- print glare
- lens blur
- unsharp mask
- crop/preview/upscale settings
- raw white balance loading settings
- display canvas/padding settings

But not the couplers? Man that would be lovely, as the saturation from the couplers is pretty cool!

---

## #714 **Mateusz Grabowski** (@Mateusz_Grabowski) · 2026-05-13 07:54

Yes that looks like highlight clipping, improper tone-mapping or wrong colour management. I had similar issues with some luts in the past. If you are using CSTs in Resolve, try changing the tone-mapping and gamut-mapping methods and maybe play around with „Use Custom Max Input” setting.

With luts in rec709 colorspace it is really important to work „under” or before them in the node sequence. There should be no edits made after the luts created with my method, otherwise things can break really easily.

---

## #715 **Mateusz Grabowski** (@Mateusz_Grabowski) · 2026-05-13 07:56

I tried to install it but it was too hard for me

[![:sweat_smile:](https://discuss.pixls.us/images/emoji/apple/sweat_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/sweat_smile.png?v=12)

But since my luts work for me I will just wait for arctic implementation.

They are for sure way more flexible and accurate than mine!

[![:slightly_smiling_face:](https://discuss.pixls.us/images/emoji/apple/slightly_smiling_face.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slightly_smiling_face.png?v=12)

---

## #716 **Mateusz Grabowski** (@Mateusz_Grabowski) · 2026-05-13 08:18

Look at the histogram without the lut applied. My guess is that brightest part on the building in your image is going „beyond” the histogram. These luts cannot handle out of gamut information. Try lowering the white-point before the lut.

I will share google drive link to some of my luts later and you will be able to troubleshoot some more

[![:slightly_smiling_face:](https://discuss.pixls.us/images/emoji/apple/slightly_smiling_face.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slightly_smiling_face.png?v=12)

---

## #717 **Ryan Cara** (@Ryan_Cara) · 2026-05-13 11:10

> **@arctic** (帖子 #600):
> ART is bypassing all the non-local and stochastic effects computing a lut, essentially encoding only the “average” output of a flat field (minus the glare that is only stochastic for now).

Any non-spatial related saturation that the couplers provide will be there!

---

## #718 **Revanza Pratamasyah** (@Revanza_Pratamasyah) · 2026-05-14 02:33

I was wondering did you change the green hue? those lushful green are amazing

---

## #719 **Mateusz Grabowski** (@Mateusz_Grabowski) · 2026-05-14 05:20

No! It is because of 5000K white balance. Spektrafilm produces very warm results out of the box so I cool everything down in camera. That and Fuji Crystal Archive paper has the best greens. Kodak stuff is just too warm for me and its greens become almost yellow.

---

## #720 **** (@Thomsen) · 2026-05-14 07:23

[@arctic](/u/arctic) or [@hanatos](/u/hanatos) Would you way it makes a difference whether you shoot uncompressed raw or compressed raw when working with the film sim?

---

## #721 **** (@Thomsen) · 2026-05-14 14:21

Also, will .dng files be sufficient?

---

## #722 **Andrea** (@arctic) · 2026-05-14 14:36

compressed raw files are not a problem. if lossless compression you just pay more compute to unpack it, if lossy compression they have smartly reduced amount of information but possibly not really perceivable. both will be treated as raw and converted to the linear rgb input of the film sim.

not super experienced with dng, but it should be just a universal standard for raw files, thus lossy/loseless depends on the original manufacturer raw. the conversion to the linear rgb input should not be a problem.

---

## #723 **Aedan** (@chaert-s) · 2026-05-14 15:49

I may have good news for you!

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

I am working on an OFX (DaVinci Resolve) port of Spektrafilm that is almost stable enough that I dare share it with everyone, however this may be mixed news for some. As I come from a Mac/iOS background, my version is currently written in Metal, Apple’s native GPU API, so it won’t immediately be available for windows sadly.

Hope to have something ready by next week to share with ya’ll!

---

## #724 **Andrea** (@arctic) · 2026-05-14 22:49

> **@Thomsen** (帖子 #566):
> ‘feel’ is a bit hard to evaluate

i am following up to this question and decided to make some comparisons. the goal is to stop a moment and evaluate the recent evolution in the “taming” of the filming stage.

this will be helpful to the sister discussion and development happening in the [spektrafilm tech thread](https://discuss.pixls.us/t/spektrafilm-tech-discussions/57512) with [@hanatos](/u/hanatos).

short summary:

- `hanatos2025` alg gives a spectra from an RGB input. it was designed to give zero errors for the human vision (standard observer)
- film sensitivities can be a bit broader than the human vision, both uv and ir side (portra 400 is one of the broadest), plus they have different shapes
- we noticed early on that reds and blues suffered, and we added an ir and uv filter to the camera after `hanatos2025` upsampling. it was eyeballed to have nice reds
- recently i tried to optimize a generic window filter per stock aiming to minimize error on real measured spectra
- more recently i tried to optimize a generic 2d exposure correction per stock (chromaticity → RGB log exposure correction)

the 2d correction is very alpha and possibly not the final solution. skin tones are still problematic, and left intentionally uncorrected here by the surface. they have peculiar reflectance spectra with a nasty dip at 550-570 nm in the green-red range, and they need care (stay tuned, more on this will come soon).

for now let’s just look at some photos and don’t get mad at me if the differences are tiny. the “feel” is made by the compounding of a lot of small things aligning together, both in life and in film simulations.

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

the following series of images are as follow:

001 - pure `hanatos2025` alg

002 - `hanatos2025` + eyeballed uv and ir filters

003 - optimized window filter per stock

004 - optimized 2d surface per stock (it is expected to make skin tones cooler, approx -0.15ev red +0.1ev blue, we’ll find a solution for this…)

all four-image groups shares the same white point, because the correction operations were designed to not affect white. which means that if for example reds of an image looks too magenta, print filters can fix that, but only the expense of ruining white and all the other correct colors.

all parameters are the same. all on portra 400 and supra endura or fuji crystal archive.

try to focus on reds, skin tones, and blues.

<div class="lightbox-wrapper">[[![car_001_hanatos2025](https://d2x313g9lpht1q.cloudfront.net/original/3X/b/0/b05969bc0ffc91c72258c65562fd6a743462b12f.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/b/0/b05969bc0ffc91c72258c65562fd6a743462b12f.jpeg)

car_001_hanatos2025640×427 177 KB](/uploads/short-url/pa3Bhud5qbg1mHbNZoCdpyVsLKv.jpeg?dl=1)

[[![car_002_hanatos2025_ir_uv](https://d2x313g9lpht1q.cloudfront.net/original/3X/b/1/b14e54668deb1459e7d66566bc81c58c44ac556a.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/b/1/b14e54668deb1459e7d66566bc81c58c44ac556a.jpeg)

car_002_hanatos2025_ir_uv640×427 178 KB](/uploads/short-url/piwkDuUlVKhUZWx1c4H1Kc1BS0G.jpeg?dl=1)

[[![car_003_hanatos2025_window](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/0/00b18e644edd93d914548bbadde4e74c2e377183.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/0/00b18e644edd93d914548bbadde4e74c2e377183.jpeg)

car_003_hanatos2025_window640×427 177 KB](/uploads/short-url/68pzqFhmanmERvG3LGtrY8dHNx.jpeg?dl=1)

[[![car_004_hanatos2025_window_surface](https://d2x313g9lpht1q.cloudfront.net/original/3X/6/d/6d4038b72aa7d16640f3d0a232272de45cf301a8.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/6/d/6d4038b72aa7d16640f3d0a232272de45cf301a8.jpeg)

car_004_hanatos2025_window_surface640×427 178 KB](/uploads/short-url/fAtDzDN6ocs0MxE5h7aItP2T25y.jpeg?dl=1)

</div>
<hr>

<div class="lightbox-wrapper">[[![portrait_001_hanatos2025](https://d2x313g9lpht1q.cloudfront.net/original/3X/f/1/f179aab8f496a07a84ca1b542e3d5f80e6f4d4b6.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/f/1/f179aab8f496a07a84ca1b542e3d5f80e6f4d4b6.jpeg)

portrait_001_hanatos2025426×640 151 KB](/uploads/short-url/ysbJUohl7DRVIIjtNqJlUKoPmrI.jpeg?dl=1)

[[![portrait_002_hanatos2025_ir_uv](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/2/523f3496dd994261e84e6f3394068f1696c98b42.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/2/523f3496dd994261e84e6f3394068f1696c98b42.jpeg)

portrait_002_hanatos2025_ir_uv426×640 151 KB](/uploads/short-url/bJAzjsMSRUTtlnsMXwC6sDLoeEa.jpeg?dl=1)

[[![portrait_003_hanatos2025_window](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/6/566faeb2ad4b7b933072e0469eb9b93b9418ba86.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/6/566faeb2ad4b7b933072e0469eb9b93b9418ba86.jpeg)

portrait_003_hanatos2025_window426×640 150 KB](/uploads/short-url/ckEl8wpCcbWTYQPAVDnWHBm4Czk.jpeg?dl=1)

[[![portrait_004_hanatos2025_window_surface](https://d2x313g9lpht1q.cloudfront.net/original/3X/6/1/619a4b76882fb2394ea18a689d5851b2b866b6b5.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/6/1/619a4b76882fb2394ea18a689d5851b2b866b6b5.jpeg)

portrait_004_hanatos2025_window_surface426×640 149 KB](/uploads/short-url/dVqT9TadIdoQavSvEQRtratkYzr.jpeg?dl=1)

</div>
<hr>

<div class="lightbox-wrapper">[[![portrait_flower_001_hanatos2025](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/1/51ecb465ae7eb56be3ee99679b44ef9af5c28224.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/1/51ecb465ae7eb56be3ee99679b44ef9af5c28224.jpeg)

portrait_flower_001_hanatos2025426×640 182 KB](/uploads/short-url/bGJOnojc0KLBGMEJE6RQDG1sSzy.jpeg?dl=1)

[[![portrait_flower_002_hanatos2025_ir_uv](https://d2x313g9lpht1q.cloudfront.net/original/3X/2/e/2ed188cf3a7916a9efdc49cf3c134800a8edb34d.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/2/e/2ed188cf3a7916a9efdc49cf3c134800a8edb34d.jpeg)

portrait_flower_002_hanatos2025_ir_uv426×640 182 KB](/uploads/short-url/6GaT7v2SvanG0AaO7V8sXbK9vsh.jpeg?dl=1)

[[![portrait_flower_003_hanatos2025_window](https://d2x313g9lpht1q.cloudfront.net/original/3X/a/5/a5c46a1f40ab7ed8b6da38ed6a9d263a0d5b79ff.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/a/5/a5c46a1f40ab7ed8b6da38ed6a9d263a0d5b79ff.jpeg)

portrait_flower_003_hanatos2025_window426×640 181 KB](/uploads/short-url/nErB7UTi9NjVqHEh5WdgSOdfCV1.jpeg?dl=1)

[[![portrait_flower_004_hanatos2025_window_surface](https://d2x313g9lpht1q.cloudfront.net/original/3X/2/1/21cdfbe69a7cdaf689f541017a0f16dc1a439ca9.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/2/1/21cdfbe69a7cdaf689f541017a0f16dc1a439ca9.jpeg)

portrait_flower_004_hanatos2025_window_surface426×640 180 KB](/uploads/short-url/4P34F089Qp6OLY677khJRvVjTcd.jpeg?dl=1)

</div>
<hr>

<div class="lightbox-wrapper">[[![portrait_leaves_001_hanatos2025](https://d2x313g9lpht1q.cloudfront.net/original/3X/d/2/d241e8797b3b10cae8d6ad8edc6f2ed463a15136.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/d/2/d241e8797b3b10cae8d6ad8edc6f2ed463a15136.jpeg)

portrait_leaves_001_hanatos2025640×427 114 KB](/uploads/short-url/u01twIW5kTni6ksSPj8F0bw5fJs.jpeg?dl=1)

[[![portrait_leaves_002_hanatos2025_ir_uv](https://d2x313g9lpht1q.cloudfront.net/original/3X/e/5/e53e43ca2ca40caf426be132983e95dab323dc53.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/e/5/e53e43ca2ca40caf426be132983e95dab323dc53.jpeg)

portrait_leaves_002_hanatos2025_ir_uv640×427 113 KB](/uploads/short-url/wHYK20SRWvvCHJ1kbSnT2RTmFY7.jpeg?dl=1)

[[![portrait_leaves_003_hanatos2025_window](https://d2x313g9lpht1q.cloudfront.net/original/3X/7/2/72b6af234e1427ad516c6ada3c257da57cb2173a.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/7/2/72b6af234e1427ad516c6ada3c257da57cb2173a.jpeg)

portrait_leaves_003_hanatos2025_window640×427 112 KB](/uploads/short-url/gmNPuKrlYiIkfJjipDNIqKrqkGu.jpeg?dl=1)

[[![portrait_leaves_004_hanatos2025_window_surface](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/c/5c8342fc82fc18af40201413c81e1ef9b1732a7b.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/c/5c8342fc82fc18af40201413c81e1ef9b1732a7b.jpeg)

portrait_leaves_004_hanatos2025_window_surface640×427 111 KB](/uploads/short-url/dcp9ymZ7GYWCdGTskpz6PtBycNd.jpeg?dl=1)

</div>
<hr>

<div class="lightbox-wrapper">[[![portrait_tree_001_hanatos2025](https://d2x313g9lpht1q.cloudfront.net/original/3X/7/9/7941b83c4afdbbff348839278db034bd307c491b.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/7/9/7941b83c4afdbbff348839278db034bd307c491b.jpeg)

portrait_tree_001_hanatos2025427×640 145 KB](/uploads/short-url/hiGzOyrlyEbGXhAF3795HpwfCwr.jpeg?dl=1)

[[![portrait_tree_002_hanatos2025_ir_uv](https://d2x313g9lpht1q.cloudfront.net/original/3X/7/7/772b696b6578c44386ac6d2afd375e74c6447312.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/7/7/772b696b6578c44386ac6d2afd375e74c6447312.jpeg)

portrait_tree_002_hanatos2025_ir_uv427×640 146 KB](/uploads/short-url/h0dPm569mvahCMwF8FqxAMZXytc.jpeg?dl=1)

[[![portrait_tree_003_hanatos2025_window](https://d2x313g9lpht1q.cloudfront.net/original/3X/d/2/d2e1f60d3a12fb1c229beff3a60ee9110682dfe6.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/d/2/d2e1f60d3a12fb1c229beff3a60ee9110682dfe6.jpeg)

portrait_tree_003_hanatos2025_window427×640 145 KB](/uploads/short-url/u5yo4DngjO1ZyZDTxBbuFC2vkNg.jpeg?dl=1)

[[![portrait_tree_004_hanatos2025_window_surface](https://d2x313g9lpht1q.cloudfront.net/original/3X/4/8/486220c08b69531a6a98bc0a1d3d00a5c60fe88d.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/4/8/486220c08b69531a6a98bc0a1d3d00a5c60fe88d.jpeg)

portrait_tree_004_hanatos2025_window_surface427×640 144 KB](/uploads/short-url/akkCbWp0k2nNmmqhQtrRMLcweoB.jpeg?dl=1)

</div>
<hr>

<div class="lightbox-wrapper">[[![sunflowers_001_hanatos2025](https://d2x313g9lpht1q.cloudfront.net/original/3X/1/f/1f9005e8c4d61a448b40a9090c740e3cf468baeb.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/1/f/1f9005e8c4d61a448b40a9090c740e3cf468baeb.jpeg)

sunflowers_001_hanatos2025426×640 166 KB](/uploads/short-url/4vdmUNT48Xs4YJpZAH0oAdnRoGT.jpeg?dl=1)

[[![sunflowers_002_hanatos2025_ir_uv](https://d2x313g9lpht1q.cloudfront.net/original/3X/4/3/436bc33d948e081fc5df6301fc8b69a9ec635fa7.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/4/3/436bc33d948e081fc5df6301fc8b69a9ec635fa7.jpeg)

sunflowers_002_hanatos2025_ir_uv426×640 165 KB](/uploads/short-url/9CqRZVYPKfburFCInwrI21i9pt5.jpeg?dl=1)

[[![sunflowers_003_hanatos2025_window](https://d2x313g9lpht1q.cloudfront.net/original/3X/3/8/384a89891da99ee531f58f3f583b30abad6d6a85.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/3/8/384a89891da99ee531f58f3f583b30abad6d6a85.jpeg)

sunflowers_003_hanatos2025_window426×640 164 KB](/uploads/short-url/81YqT09sGE0g0TdDi86LTMe3hKl.jpeg?dl=1)

[[![sunflowers_004_hanatos2025_window_surface](https://d2x313g9lpht1q.cloudfront.net/original/3X/7/d/7d59acccabb235e91015f36b1b8913e4b480b6d4.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/7/d/7d59acccabb235e91015f36b1b8913e4b480b6d4.jpeg)

sunflowers_004_hanatos2025_window_surface426×640 164 KB](/uploads/short-url/hSTOjNNmfeu1eOqqMCj2IPrFtCA.jpeg?dl=1)

</div>

a few comments (opinions too, do not take it as science):

- unfiltered `hanatos2025` has the most saturation because the uv and ir tails increase channel separation. when we had it unfiltered at the very beginning, the couplers were also lower. each correction 001–>002–>003–>004 tamed the saturations of the overshooting colors, but also added saturation to the undersaturated ones (less flashy and goes a bit unnoticed).
- couplers were steadily increased over time thanks to the taming of the overshooting saturation. at the very beginning with just `hanatos2025` we could not afford a big amount of inter-image effects because the image would break quite quickly. now we have more headroom because the colors are more balanced in saturation.
- this is not a matter of color preference, but more to try to go after what are the most accurate colors. color preferences can be added on top (saturation, color shifts etc). to be verified is the fact that a more “correct” simulation should give better skin tones.

finally also the image from [@Anthonygansauer](/u/anthonygansauer). i didn’t spend a lot of efforts to try to match the scan, but i will try again when the filming alg will settle. you can notice the colors that are mainly changing in the target.

<div class="lightbox-wrapper">[[![antony_target_001_hanatos2025](https://d2x313g9lpht1q.cloudfront.net/original/3X/a/d/ad94e71b7c075e6fc38defdf9f48568ee4c352e7.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/a/d/ad94e71b7c075e6fc38defdf9f48568ee4c352e7.jpeg)

antony_target_001_hanatos2025640×426 127 KB](/uploads/short-url/oLzCKPAjdqpqdQfXd4ui77mhgAT.jpeg?dl=1)

[[![antony_target_002_hanatos2025_ir_uv](https://d2x313g9lpht1q.cloudfront.net/original/3X/3/7/376b41f8d2e52e69424d0d9a350bfc80c6d00b8f.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/3/7/376b41f8d2e52e69424d0d9a350bfc80c6d00b8f.jpeg)

antony_target_002_hanatos2025_ir_uv640×426 128 KB](/uploads/short-url/7Ug3Gv3X9b1lxoAXlLHM9KKvNuv.jpeg?dl=1)

[[![antony_target_003_hanatos2025_window](https://d2x313g9lpht1q.cloudfront.net/original/3X/9/2/9296a3b8c95c77819e63b45b034f66eb8a602386.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/9/2/9296a3b8c95c77819e63b45b034f66eb8a602386.jpeg)

antony_target_003_hanatos2025_window640×426 128 KB](/uploads/short-url/kUMsaK9SlKvF02WAwa0KppXxGcK.jpeg?dl=1)

[[![antony_target_004_hanatos2025_window_surface](https://d2x313g9lpht1q.cloudfront.net/original/3X/2/a/2aa2cd706ad2901174f587f12b028c07adb52f16.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/2/a/2aa2cd706ad2901174f587f12b028c07adb52f16.jpeg)

antony_target_004_hanatos2025_window_surface640×426 127 KB](/uploads/short-url/65aR6nJukIrjPSKVaJN2HZ26h38.jpeg?dl=1)

</div>

and the reference ra-4 printed

[[![antony_target_005_analog](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/9/f933e483473c0d7e456df2fb8eb754168c081dea_2_690x551.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/9/f933e483473c0d7e456df2fb8eb754168c081dea_2_690x551.jpeg)

antony_target_005_analog1208×965 168 KB](/uploads/short-url/zyy4ju1m0eQNkygFOqciaE6c8lQ.jpeg?dl=1)

---

## #725 **Tim** (@Soupy) · 2026-05-15 00:31

Viewing on a wide gamut calibrated monitor, going off the very unscientific “feel”, I prefer 003 in nearly all cases, typically followed by 004 and 002. However, comparing the image from [@Anthonygansauer](/u/anthonygansauer) 004 looks the closest match to me.

---

## #726 **Bob** (@PhotoPhysicsGuy) · 2026-05-15 01:48

Same here. Just by ‘feel’ its 003 all the way. Comparing to the RA-4 scan its 004. The colorchecker patches show a lot more saturation for the sims compared to the RA-4 scan. The champagne flutes too. Has the coupler strength gone too high maybe?

---

*本文档由 Discourse 抓取工具自动生成*
*原始链接: https://discuss.pixls.us/t/48209*
