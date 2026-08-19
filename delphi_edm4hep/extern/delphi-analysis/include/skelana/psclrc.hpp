#ifndef SKELANA_PSCLRC_HPP
#define SKELANA_PSCLRC_HPP

#include "skelana/mtrack.hpp"

namespace skelana
{
/*+KEEP,PSCLRC.                Barrel RICH liquid information
*                            ( PA extra-module HAID (26) )
*
*     NLRIC                - Number of tracks with RICH liq
*     LENLRC               - Length of RICH liq information
*     QLRIC(LENLRC,MTRACK) - Real    array of RICH liq information
*     KLRIC(LENLRC,MTRACK) - Integer array of RICH liq information
*
*     QLRIC(1,I) - THEL , Cerenkov angle in liquid
*     QLRIC(2,I) - SIGL , Cerenkov angle resolution
*     KLRIC(3,I) - NPHL , Number of photoelectrons in ring
*     QLRIC(4,I) - NEPL , Expected number of photoel. in liquid
*     KLRIC(5,I) - FLAGL, RICH sector flag in liquid
*
* Fortran COMMON layout (stdcdes.car +KEEP,PSCLRC):
*   INTEGER NPHL, NEPL                         <- NEPL is INTEGER
*   REAL    THEL, SIGL, FLAGL                  <- FLAGL is REAL
*   COMMON /PSCLRC/ NLRIC, KLRIC(LENLRC,MTRACK),
*  +                THEL(MTRACK), SIGL(MTRACK),
*  +                NPHL(MTRACK), NEPL(MTRACK),
*  +                FLAGL(MTRACK)
*
* PRIOR BUG (Codex mppqrb2p): nepl declared float but Fortran has it
* as INTEGER; flagl declared int but Fortran has it as REAL.
* Liquid plot still mostly worked because π saturation dominates and
* the per-track THEL/SIGL/NPHL slots happened to land in the right
* memory region even with the wrong types; gas was much more sensitive
* to the layout drift via PSCGRC's extra [6] column bug.
*/
    inline const int LENLRC = 5;
    extern "C" struct
    {
        int   nlric;
        int   klric[MTRACK][LENLRC];
        float thel[MTRACK];
        float sigl[MTRACK];
        int   nphl[MTRACK];
        int   nepl[MTRACK];      // INTEGER (was float — bug)
        float flagl[MTRACK];     // REAL (was int — bug)
    } psclrc_;

    inline int &NLRIC = psclrc_.nlric;
    inline int   &KLRIC(int i, int j) { return psclrc_.klric[j - 1][i - 1]; }
    inline float &QLRIC(int i, int j) { return *reinterpret_cast<float*>(&psclrc_.klric[j - 1][i - 1]); }
    inline float &THEL (int i) { return psclrc_.thel[i - 1]; }
    inline float &SIGL (int i) { return psclrc_.sigl[i - 1]; }
    inline int   &NPHL (int i) { return psclrc_.nphl[i - 1]; }
    inline int   &NEPL (int i) { return psclrc_.nepl[i - 1]; }
    inline float &FLAGL(int i) { return psclrc_.flagl[i - 1]; }
} // namespace skelana

#endif // SKELANA_PSCLRC_HPP
