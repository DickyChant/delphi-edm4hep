#ifndef SKELANA_PSCBTG_HPP
#define SKELANA_PSCBTG_HPP

namespace skelana
{
/*    +KEEP,PSCBTG.                      B tagging information
*                                          ( BTAG bank (25) )
*
*     QBTPRN(1) - B tagging probability for tracks with         m s l
*                 negative impact parameter, hemisphere1
*     QBTPRN(2) - B tagging probability for tracks with         m s l
*                 negative impact parameter, hemisphere2
*     QBTPRN(3) - B tagging probability for tracks with         m s l
*                 negative impact parameter, whole event
*     QBTPRP(1) - B tagging probability for tracks with         m s l
*                 positive impact parameter, hemisphere1
*     QBTPRP(2) - B tagging probability for tracks with         m s l
*                 positive impact parameter, hemisphere2
*     QBTPRP(3) - B tagging probability for tracks with         m s l
*                 positive impact parameter, whole event
*     QBTPRS(1) - B tagging probability for all tracks,         - s l
*                                            hemisphere1
*     QBTPRS(2) - B tagging probability for all tracks,         - s l
*                                            hemisphere2
*     QBTPRS(3) - B tagging probability for all tracks,         - s l
*                                            whole event
*     QBTTHR(1) - X thrust axis component from B tagging        - s l
*     QBTTHR(2) - Y thrust axis component from B tagging        - s l
*     QBTTHR(3) - Z thrust axis component from B tagging        - s l
*     QBTTHR(4) - Thrust value                                  - - -
*/
    extern "C" struct
    {
        float qbtprn[3];
        float qbtprp[3];
        float qbtprs[3];
        float qbtthr[4];
    } pscbtg_;

    inline float &QBTPRN(int i) { return pscbtg_.qbtprn[i - 1]; }
    inline float &QBTPRP(int i) { return pscbtg_.qbtprp[i - 1]; }
    inline float &QBTPRS(int i) { return pscbtg_.qbtprs[i - 1]; }
    inline float &QBTTHR(int i) { return pscbtg_.qbtthr[i - 1]; }
} // namespace skelana

#endif // SKELANA_PSCBTG_HPP
