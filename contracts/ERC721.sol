// SPDX-License-Identifier: MIT
pragma solidity ^0.4.25;

/**
 * @title ERC721 非同质化代币实训合约
 * @dev 实现标准 ERC721 接口，配合 NFT 仿真交易市场使用。
 */
contract ERC721 {
    string public name;
    string public symbol;

    mapping(uint256 => address) public ownerOf;
    mapping(address => uint256) public balanceOf;
    mapping(uint256 => address) public approved;
    mapping(address => mapping(address => bool)) public isApprovedForAll;
    mapping(uint256 => string) public tokenURI;

    event Transfer(address indexed from, address indexed to, uint256 indexed tokenId);
    event Approval(address indexed owner, address indexed approved, uint256 indexed tokenId);
    event ApprovalForAll(address indexed owner, address indexed operator, bool approved);

    constructor(string _name, string _symbol) public {
        name = _name;
        symbol = _symbol;
    }

    function mint(address _to, uint256 _tokenId, string _tokenURI) public {
        require(_to != address(0), "ERC721: mint to zero address");
        require(ownerOf[_tokenId] == address(0), "ERC721: token already minted");
        ownerOf[_tokenId] = _to;
        balanceOf[_to]++;
        tokenURI[_tokenId] = _tokenURI;
        emit Transfer(address(0), _to, _tokenId);
    }

    function transferFrom(address _from, address _to, uint256 _tokenId) public {
        require(ownerOf[_tokenId] == _from, "ERC721: not owner");
        require(_to != address(0), "ERC721: transfer to zero address");
        require(
            msg.sender == _from || approved[_tokenId] == msg.sender || isApprovedForAll[_from][msg.sender],
            "ERC721: not approved"
        );
        balanceOf[_from]--;
        balanceOf[_to]++;
        ownerOf[_tokenId] = _to;
        approved[_tokenId] = address(0);
        emit Transfer(_from, _to, _tokenId);
    }

    function approve(address _approved, uint256 _tokenId) public {
        require(ownerOf[_tokenId] == msg.sender, "ERC721: not owner");
        approved[_tokenId] = _approved;
        emit Approval(msg.sender, _approved, _tokenId);
    }

    function setApprovalForAll(address _operator, bool _approved) public {
        isApprovedForAll[msg.sender][_operator] = _approved;
        emit ApprovalForAll(msg.sender, _operator, _approved);
    }
}
