#ifndef SKELANA_PSCHAD_HPP
#define SKELANA_PSCHAD_HPP

#include "skelana/mtrack.hpp"

namespace skelana
{
/* +KEEP,PSCHAD.                Hadron identification information
*                            ( PA extra-module HAID (26) )
*
*     NHAID                - Number of identified hadrons
*     LENHAD               - Length of the had.id. information
*     QHAID(LENHAD,MTRACK) - Real    array of HAID information
*     KHAID(LENHAD,MTRACK) - Integer array of HAID information
*
*     KHAID(1,I) - ISIGN   , Used for combined tag
*     KHAID(2,I) - IDKAON  , Kaon   siganture with DEDX
*     KHAID(3,I) - IDPROTON, Proton signature with DEDX
*     KHAID(4,I) - IKAON   , Kaon   siganture with RICH
*     KHAID(5,I) - IPROTON , Proton signature with RICH
*     KHAID(6,I) - IPION   , Pion   signature with RICH
*     QHAID(7,I) - XKAON   , Combined kaon     tag
*     QHAID(8,I) - XPROTON , Combined proton   tag
*     KHAID(9,I) -           RICH quality status
*
*/
    inline const int LENHAD = 9;
    extern "C" struct
    {
        int nhaid;
        int khaid[MTRACK][LENHAD];
    } pschad_;

    inline int &NHAID = pschad_.nhaid;
    inline int &KHAID(int i, int j) { return pschad_.khaid[j - 1][i - 1]; }
    inline float &QHAID(int i, int j) { return *reinterpret_cast<float *>(&pschad_.khaid[j - 1][i - 1]); }

}   // namespace skelana

#endif // SKELANA_PSCHAD_HPP