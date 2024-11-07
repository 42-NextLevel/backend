// SPDX-License-Identifier: GPL-3.0

pragma solidity >=0.8.2 <0.9.0;

/**
 * @title Storage
 * @dev Store & retrieve value in a variable
 * @custom:dev-run-script ./scripts/deploy_with_ethers.ts
 */


// 구현을 바꿀 수도 있음 -> 유저가 메타마스크 회원가입 하게 할 수도 있다.
contract PongHistory {
    
    struct MatchInfo {
        uint256 startTime;
	    uint8 matchType;
	    bytes16 user1;
	    bytes16 user2;
        bytes16 nick1;
        bytes16 nick2;
        uint8 score1;
        uint8 score2;	
    }

    address public admin;
    mapping(uint16 gameId => MatchInfo Match) public table;

    constructor () {
        admin = msg.sender;
    }

    event HistoryAdded(uint32 indexed gameId, uint32 startTime, bytes16 user1, bytes16 user2);
    event AdminChanged(address indexed oldAdmin, address indexed newAdmin);

    modifier onlyAdmin() {
        require (msg.sender == admin, "Only admin can add history");
        _;
    }

    function addHistory(uint16 gameId, MatchInfo memory info) external onlyAdmin {
        require(info.startTime > 0, "Invalid start time");
        require(info.startTime <= block.timestamp, "Start time cannot be in the future");
        table[gameId] = info;
    }

    function getHistory(uint16 gameId) public view returns(MatchInfo memory)  {
        return table[gameId];
    }

    function changeAdmin(address newAdmin) external onlyAdmin {
        require(newAdmin != address(0), "Invalid address");
        require(newAdmin != admin, "New admin cannot be the same as the current admin");
        emit AdminChanged(admin, newAdmin);
        admin = newAdmin;
    }
}