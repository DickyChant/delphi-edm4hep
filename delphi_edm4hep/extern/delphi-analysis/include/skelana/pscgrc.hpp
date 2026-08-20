#ifndef SKELETON_PSCGRC_HPP
#define SKELETON_PSCGRC_HPP

#include "skelana/mtrack.hpp"

namespace skelana
{
/*+KEEP,PSCGRC.                     RICH Gas information
*                            ( PA extra-module HAID (26) )
*
*     NGRIC                - Number of tracks with RICH gas info
*     QGRIC(LENGRC,MTRACK) - Real    array of RICH gas information
*     KGRIC(LENGRC,MTRACK) - Integer array of RICH gas information
*
*     QGRIC(1,I) - THEG , Cerenkov angle in gas
*     QGRIC(2,I) - SIGG , Cerenkov angle resolution
*     KGRIC(3,I) - NPHG , Number of photoelectrons in ring
*     QGRIC(4,I) - NEPG , Expected number of photoel. in gas
*     KGRIC(5,I) - FLAGG, RICH sector flag in gas
*
* Fortran COMMON layout (stdcdes.car +KEEP,PSCGRC):
*   PARAMETER LENGRC = 5
*   INTEGER NPHG, NEPG                         <- NEPG is INTEGER
*   REAL    THEG, SIGG, FLAGG                  <- FLAGG is REAL
*   COMMON /PSCGRC/ NGRIC, KGRIC(LENGRC,MTRACK),
*  +                THEG(MTRACK), SIGG(MTRACK),
*  +                NPHG(MTRACK), NEPG(MTRACK),
*  +                FLAGG(MTRACK)
*
* PRIOR BUG (gas-RICH plot didn't match DELPHI 1994 — Codex mppqrb2p):
*   - kgric was declared [MTRACK][6] instead of [MTRACK][5] (LENGRC=5)
*     -> shifted ALL subsequent arrays by MTRACK*sizeof(int) bytes,
*        meaning THEG()/SIGG()/NPHG()/NEPG()/FLAGG() were reading
*        uninitialized / garbage memory.
*   - nepg was declared float but Fortran COMMON has it as INTEGER
*   - flagg was declared int but Fortran COMMON has it as REAL
*/
    extern "C" struct
    {
        int   ngric;
        int   kgric[MTRACK][5];   // LENGRC = 5 (was 6 — bug)
        float theg[MTRACK];
        float sigg[MTRACK];
        int   nphg[MTRACK];
        int   nepg[MTRACK];       // INTEGER (was float — bug)
        float flagg[MTRACK];      // REAL (was int — bug)
    } pscgrc_;

    inline int &NGRIC = pscgrc_.ngric;
    inline int   &KGRIC(int i, int j) { return pscgrc_.kgric[j - 1][i - 1]; }
    inline float &QGRIC(int i, int j) { return *reinterpret_cast<float*>(&pscgrc_.kgric[j - 1][i - 1]); }
    inline float &THEG (int i) { return pscgrc_.theg[i - 1]; }
    inline float &SIGG (int i) { return pscgrc_.sigg[i - 1]; }
    inline int   &NPHG (int i) { return pscgrc_.nphg[i - 1]; }
    inline int   &NEPG (int i) { return pscgrc_.nepg[i - 1]; }
    inline float &FLAGG(int i) { return pscgrc_.flagg[i - 1]; }
} // namespace skelana

#endif // SKELETON_PSCGRC_HPP
